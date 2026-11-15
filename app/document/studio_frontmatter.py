"""Portable PDF import and independently editable cover/title-page layers."""
import base64
import html
from pathlib import Path
import pymupdf
from app.fonts.font_manager import FontManager


def import_pdf(path):
    data = Path(path).read_bytes()
    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ValueError("Unlock this PDF before importing it.")
        for index, page in enumerate(pdf):
            text = page.get_text()
            markup = "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"
            pages.append({"number": index + 1, "width": page.rect.width, "height": page.rect.height,
                          "source": "", "html": markup, "imported_html": markup,
                          "history": [], "pdf_index": index, "edited": False})
    return {"format": "translation-studio-v1", "source_path": str(Path(path).resolve()),
            "pdf_base": base64.b64encode(data).decode("ascii"), "pages": pages}


def default_frontmatter(kind="cover"):
    return {"kind": kind, "title": "পার্থক্য ও পুনরাবৃত্তি", "author": "জিল দেলুস",
            "translator": "সুশেন বিশ্বাস", "english_translator": "পল প্যাটন",
            "editor": "শাহ আলম প্রধান", "publisher": "ম্যাসস্টকস",
            "show_english": False, "background": "", "color": "#172033",
            "title_y": 18, "author_y": 37, "translator_y": 51, "title_size": 40,
            "credit_size": 12, "panel": True, "panel_opacity": 5,
            "layout": "translator_focus", "translator_size": 32, "author_size": 18, "support_y": 78}


def replace_frontmatter(page, design):
    from copy import deepcopy
    from datetime import datetime
    page["history"].append({"at": datetime.now().isoformat(), "html": page["html"],
                            "frontmatter": deepcopy(page.get("frontmatter")), "edited": page.get("edited", True)})
    page["frontmatter"] = deepcopy(design)
    page["edited"] = True


def render_frontmatter(pdf, item):
    design = item["frontmatter"]
    page = pdf.new_page(width=item["width"], height=item["height"])
    page.draw_rect(page.rect, color=None, fill=(0.96, 0.95, 0.91))
    if design.get("background"):
        page.insert_image(page.rect, stream=base64.b64decode(design["background"], validate=True), keep_proportion=True)
    if design.get("panel", True):
        page.draw_rect(pymupdf.Rect(page.rect.width * .08, page.rect.height * .12,
                                   page.rect.width * .92, page.rect.height * .89),
                       color=None, fill=(1, 1, 1),
                       fill_opacity=max(0, min(100, float(design.get("panel_opacity", 92)))) / 100)
    font = FontManager.get_instance().get_font_path("Noto Sans Bengali")
    css = f"@font-face {{font-family:Bangla;src:url({font.name});}} body {{font-family:Bangla;margin:0; text-align:center; color:{design['color']};}}"
    archive = pymupdf.Archive(str(font.parent))
    credits = "বাংলা অনুবাদ: " + design["translator"]
    if design.get("show_english") and design.get("english_translator"):
        credits += "\nইংরেজি অনুবাদ: " + design["english_translator"]
    if design.get("editor", "").strip():
        credits += "\nসম্পাদক: " + design["editor"].strip()
    if design.get("publisher", "").strip():
        credits += "\nপ্রকাশনা: " + design["publisher"].strip()
    def text_markup(text, size):
        return f'<div style="font-size:{size}pt">' + html.escape(text).replace("\n", "<br>") + '</div>'
    if design.get("layout") == "translator_focus":
        supporting = []
        if design.get("show_english") and design.get("english_translator"):
            supporting.append("ইংরেজি অনুবাদ: " + design["english_translator"])
        for key, label in (("editor", "সম্পাদক"), ("publisher", "প্রকাশনা")):
            if design.get(key, "").strip():
                supporting.append(label + ": " + design[key].strip())
        layers = [
            (text_markup(design["title"], design["title_size"]), design["title_y"]),
            (text_markup("মূল রচনা", 10) + text_markup(design["author"], design.get("author_size", 18)), design["author_y"]),
            (text_markup("বাংলা অনুবাদ", 12) + text_markup(design["translator"], design.get("translator_size", 32)), design["translator_y"])]
        if supporting:
            layers.append((text_markup("\n".join(supporting), design["credit_size"]), design.get("support_y", 78)))
    else:
        layers = [(text_markup(design["title"], design["title_size"]), design["title_y"]),
                  (text_markup(design["author"], design["credit_size"]), design["author_y"]),
                  (text_markup(credits, design["credit_size"]), design["translator_y"])]
    # Each layer has its own text box. Reject overlaps rather than hiding text.
    layers.sort(key=lambda layer: layer[1])
    for index, (markup, y) in enumerate(layers):
        top = page.rect.height * y / 100
        bottom = min(page.rect.height * .88,
                     page.rect.height * layers[index + 1][1] / 100 - 12 if index + 1 < len(layers) else page.rect.height * .88)
        rect = pymupdf.Rect(page.rect.width * .12, top, page.rect.width * .88, bottom)
        if rect.height <= 0:
            raise ValueError("Cover text layers overlap. Adjust their vertical positions.")
        spare, scale = page.insert_htmlbox(rect, markup, css=css, archive=archive, scale_low=1)
        if spare < 0:
            raise ValueError("Cover text does not fit. Reduce its font size or adjust layer positions.")
