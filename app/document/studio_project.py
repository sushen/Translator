"""Independent, portable page-editor projects; no writes to translation jobs."""
import base64
import html
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from contextlib import ExitStack

import pymupdf

from app.fonts.font_manager import FontManager


def from_document(document):
    pages = []
    for page in document.pages:
        paragraphs = [p for p in page.paragraphs if not p.is_page_number]
        pictures = "".join('<p><img width="300" src="data:image/png;base64,' +
                           base64.b64encode(block.image_bytes).decode("ascii") + '" /></p>'
                           for block in page.blocks if block.block_type == "image" and block.image_bytes)
        pages.append({"number": page.page_num, "width": page.width, "height": page.height,
                      "source": "\n\n".join(p.source_text for p in paragraphs),
                      "html": pictures + "".join("<p>" + html.escape(p.current_translation).replace("\n", "<br>") + "</p>"
                                      for p in paragraphs), "history": []})
    return {"format": "translation-studio-v1", "source_path": str(document.file_path), "pages": pages}


def save_project(project, path):
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Save studio projects with a .json extension.")
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(project, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_project(path):
    project = json.loads(Path(path).read_text(encoding="utf-8"))
    if project.get("format") != "translation-studio-v1" or not project.get("pages"):
        raise ValueError("Not a Translation Studio project.")
    for page in project["pages"]:
        if not isinstance(page.get("html"), str) or not isinstance(page.get("source"), str):
            raise ValueError("Invalid page content.")
        if not (100 <= float(page["width"]) <= 5000 and 100 <= float(page["height"]) <= 5000):
            raise ValueError("Invalid page dimensions.")
    return project


def record_page(page, markup):
    if page["html"] != markup:
        page["history"].append({"at": datetime.now().isoformat(), "html": page["html"]})
        page["html"] = markup


def render_project(project, return_mapping=False):
    """Keep source pages separate and paginate overflow without shrinking fonts."""
    from app.pdf.page_flow import append_source_page
    font = FontManager.get_instance().get_font_path("Noto Sans Bengali")
    css = f"@font-face {{font-family: bangla; src: url({font.name});}} body {{font-family:bangla; font-size:11pt;}}"
    with ExitStack() as stack, pymupdf.open() as pdf:
        original_pdf = (stack.enter_context(pymupdf.open(stream=base64.b64decode(project["pdf_base"]), filetype="pdf"))
                        if project.get("pdf_base") else None)
        mapping = []
        toc = []
        for item in project["pages"]:
            number = item.get("number", len(mapping) + 1)
            if item.get("frontmatter"):
                from app.document.studio_frontmatter import render_frontmatter
                index = len(pdf)
                render_frontmatter(pdf, item)
                mapping.append([index])
                toc.append([1, f"Source page {number}", index + 1])
                continue
            if "pdf_index" in item and not item.get("edited"):
                index = len(pdf)
                pdf.insert_pdf(original_pdf, from_page=item["pdf_index"], to_page=item["pdf_index"], final=0)
                mapping.append([index])
                toc.append([1, f"Source page {number}", index + 1])
                continue
            content = item["html"]
            # Inline images are embedded into the project. Resolve them locally
            # for MuPDF without allowing arbitrary file or network resources.
            import re
            with tempfile.TemporaryDirectory() as folder:
                def image_source(match):
                    value = match.group(1)
                    if not value.startswith("data:image/") or ";base64," not in value:
                        raise ValueError("Only embedded images are supported.")
                    name = f"image_{len(list(Path(folder).iterdir()))}.png"
                    Path(folder, name).write_bytes(base64.b64decode(value.split(",", 1)[1], validate=True))
                    return f'src="{name}"'
                content = re.sub(r'src="([^"]*)"', image_source, content)
                resources = pymupdf.Archive(folder)
                resources.add(str(font.parent))
                indices = append_source_page(pdf, content, item["width"], item["height"],
                    pymupdf.Rect(36, 36, item["width"] - 36, item["height"] - 42), css, resources)
                mapping.append(indices)
                number = item.get("number", len(mapping))
                toc.append([1, f"Source page {number}", indices[0] + 1])
                for continuation, index in enumerate(indices):
                    label = f"Source page {number}"
                    if continuation:
                        label += f" - continued {continuation + 1}"
                    pdf[index].insert_textbox(pymupdf.Rect(36, item["height"] - 30,
                        item["width"] - 36, item["height"] - 12), label, fontsize=8, align=1)
        pdf.set_toc(toc)
        result = pdf.tobytes()
        return (result, mapping) if return_mapping else result
