import pymupdf
import html
import tempfile
from pathlib import Path
from typing import List, Optional
from app.document.document_model import DocumentModel
from app.fonts.font_manager import FontManager
from app.utils.paths import get_output_dir, get_font_path
from app.utils.logging import get_logger

logger = get_logger(__name__)

class PDFBuilder:
    def __init__(self, font_name: str = "Noto Sans Bengali"):
        self.font_name = font_name
        self.font_manager = FontManager.get_instance()
        self.font_path = self.font_manager.get_font_path(font_name) or get_font_path("NotoSansBengali-Regular.ttf")

    def get_safe_output_path(self, source_path: Path, output_dir: Optional[Path] = None) -> Path:
        target_dir = output_dir or get_output_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        stem = source_path.stem
        candidate = target_dir / f"{stem}_Bangla.pdf"
        counter = 2
        while candidate.exists():
            candidate = target_dir / f"{stem}_Bangla_{counter}.pdf"
            counter += 1

        return candidate

    def build_pdf(
        self,
        document_model: DocumentModel,
        output_path: Optional[Path] = None,
        preserve_images: bool = True,
        preserve_page_numbers: bool = True,
        keep_page_breaks: bool = True
    ) -> Path:
        out_file = output_path or self.get_safe_output_path(document_model.file_path)
        if keep_page_breaks:
            return self._build_source_pages(document_model, out_file, preserve_images, preserve_page_numbers)

        doc = pymupdf.open()
        archive = pymupdf.Archive(str(self.font_path.parent))

        margin = 50.0
        css = f"""
        <style>
        @font-face {{
            font-family: NotoSansBengali;
            src: url({self.font_path.name});
        }}
        body {{
            font-family: NotoSansBengali;
            font-size: 11pt;
            line-height: 1.5;
            color: #111111;
        }}
        h1 {{
            font-family: NotoSansBengali;
            font-size: 18pt;
            font-weight: bold;
            text-align: center;
            margin-top: 15px;
            margin-bottom: 12px;
        }}
        p {{
            font-family: NotoSansBengali;
            font-size: 11pt;
            margin-top: 0px;
            margin-bottom: 8px;
            text-indent: 15px;
            text-align: justify;
        }}
        .page-num {{
            font-family: NotoSansBengali;
            font-size: 9pt;
            text-align: center;
            color: #666666;
            margin-top: 10px;
        }}
        </style>
        """

        def create_new_page(w: float = 595.0, h: float = 842.0):
            return doc.new_page(width=w, height=h)

        if keep_page_breaks:
            # Render page by page strictly
            for page_model in document_model.pages:
                page = create_new_page(page_model.width, page_model.height)
                y_curr = margin
                content_w = page_model.width - 2 * margin

                # Draw images if any
                if preserve_images:
                    for block in page_model.blocks:
                        if block.block_type == "image" and block.image_bytes:
                            try:
                                rect = pymupdf.Rect(*block.bbox)
                                page.insert_image(rect, stream=block.image_bytes)
                            except Exception as e:
                                logger.warning(f"Failed to insert image on page {page_model.page_num}: {e}")

                # Draw paragraphs
                for para in page_model.paragraphs:
                    if para.is_page_number:
                        if preserve_page_numbers:
                            num_html = f"{css}<div class='page-num'>- {para.text} -</div>"
                            num_rect = pymupdf.Rect(margin, page_model.height - 40, margin + content_w, page_model.height - 15)
                            page.insert_htmlbox(num_rect, num_html, archive=archive)
                        continue

                    text_to_render = para.translated_text if para.translated_text else para.text
                    if not text_to_render.strip():
                        continue

                    html_snippet = f"{css}<h1>{text_to_render}</h1>" if para.is_heading else f"{css}<p>{text_to_render}</p>"
                    box_h = 45.0 if para.is_heading else max(30.0, len(text_to_render) * 0.4)

                    if y_curr + box_h > page_model.height - margin:
                        page = create_new_page(page_model.width, page_model.height)
                        y_curr = margin

                    rect = pymupdf.Rect(margin, y_curr, margin + content_w, y_curr + box_h)
                    spare_h, scale = page.insert_htmlbox(rect, html_snippet, archive=archive)
                    used_h = box_h - spare_h
                    y_curr += used_h + 4.0

        else:
            # Reflow entire document naturally across pages
            page_w, page_h = 595.0, 842.0
            content_w = page_w - 2 * margin
            page = create_new_page(page_w, page_h)
            y_curr = margin
            current_page_num = 1

            for page_model in document_model.pages:
                # Add images first for page
                if preserve_images:
                    for block in page_model.blocks:
                        if block.block_type == "image" and block.image_bytes:
                            try:
                                img_h = block.bbox[3] - block.bbox[1]
                                if y_curr + img_h > page_h - margin:
                                    page = create_new_page(page_w, page_h)
                                    y_curr = margin
                                    current_page_num += 1
                                rect = pymupdf.Rect(margin, y_curr, margin + (block.bbox[2] - block.bbox[0]), y_curr + img_h)
                                page.insert_image(rect, stream=block.image_bytes)
                                y_curr += img_h + 10.0
                            except Exception as e:
                                logger.warning(f"Failed inserting image: {e}")

                for para in page_model.paragraphs:
                    if para.is_page_number:
                        continue  # Let reflow handle page numbers dynamically

                    text_to_render = para.translated_text if para.translated_text else para.text
                    if not text_to_render.strip():
                        continue

                    html_snippet = f"{css}<h1>{text_to_render}</h1>" if para.is_heading else f"{css}<p>{text_to_render}</p>"
                    box_h = 50.0 if para.is_heading else max(35.0, len(text_to_render) * 0.35)

                    if y_curr + box_h > page_h - margin - 30:
                        if preserve_page_numbers:
                            num_html = f"{css}<div class='page-num'>- {current_page_num} -</div>"
                            num_rect = pymupdf.Rect(margin, page_h - 40, margin + content_w, page_h - 15)
                            page.insert_htmlbox(num_rect, num_html, archive=archive)

                        page = create_new_page(page_w, page_h)
                        y_curr = margin
                        current_page_num += 1

                    rect = pymupdf.Rect(margin, y_curr, margin + content_w, y_curr + box_h)
                    spare_h, scale = page.insert_htmlbox(rect, html_snippet, archive=archive)
                    used_h = box_h - spare_h
                    y_curr += used_h + 4.0

            if preserve_page_numbers:
                num_html = f"{css}<div class='page-num'>- {current_page_num} -</div>"
                num_rect = pymupdf.Rect(margin, page_h - 40, margin + content_w, page_h - 15)
                page.insert_htmlbox(num_rect, num_html, archive=archive)

        doc.save(str(out_file))
        doc.close()
        logger.info(f"Bangla PDF generated successfully at: {out_file}")
        return out_file

    def _build_source_pages(self, document, out_file, preserve_images, preserve_numbers):
        from app.pdf.page_flow import append_source_page
        self.last_page_map = []
        with pymupdf.open() as output, tempfile.TemporaryDirectory() as folder:
            archive = pymupdf.Archive(folder)
            archive.add(str(self.font_path.parent))
            css = f"""@font-face {{font-family: Bangla; src:url({self.font_path.name});}}
                body {{font-family:Bangla; font-size:12pt; line-height:1.4; margin:0;}}
                p {{margin:0 0 9pt 0; text-align:justify;}}
                h1 {{margin:0 0 14pt 0; text-align:center; font-weight:bold;}}
                img {{max-width:100%;}}"""
            toc = []
            for source in document.pages:
                paragraphs = [p for p in source.paragraphs if not p.is_page_number]
                boxes = [p.bbox for p in paragraphs if p.bbox and p.bbox[2] > p.bbox[0]]
                left = max(24, min((b[0] for b in boxes), default=50))
                right = min(source.width - 24, max((b[2] for b in boxes), default=source.width - 50))
                top = max(24, min((b[1] for b in boxes), default=50))
                if right - left < 100 or top > source.height - 100:
                    left, right, top = 36, source.width - 36, 36
                items = []
                for index, paragraph in enumerate(paragraphs):
                    text = html.escape(paragraph.current_translation or paragraph.source_text).replace("\n", "<br>")
                    font = max(11, min(20 if paragraph.is_heading else 14, paragraph.font_size))
                    tag = "h1" if paragraph.is_heading else "p"
                    markup = f'<{tag} style="font-size:{font}pt">{text}</{tag}>'
                    y = paragraph.bbox[1] if paragraph.bbox else index * 20
                    bottom = paragraph.bbox[3] if paragraph.bbox else y + 20
                    items.append((y, bottom, markup))
                if preserve_images:
                    for index, block in enumerate(source.blocks):
                        if block.block_type == "image" and block.image_bytes:
                            name = f"image_{source.page_num}_{index}.png"
                            Path(folder, name).write_bytes(block.image_bytes)
                            width = min(right - left, block.bbox[2] - block.bbox[0])
                            height = width * (block.bbox[3] - block.bbox[1]) / max(1, block.bbox[2] - block.bbox[0])
                            height_limit = source.height - top - 45
                            if height > height_limit:
                                width *= height_limit / height
                                height = height_limit
                            items.append((block.bbox[1], block.bbox[3], f'<p><img src="{name}" width="{width}" height="{height}"></p>'))
                content = []
                previous_bottom = None
                for y, bottom, markup in sorted(items, key=lambda item:item[0]):
                    gap = max(0, y - previous_bottom - 9) if previous_bottom is not None else 0
                    content.append(f'<div style="margin-top:{gap}pt">{markup}</div>')
                    previous_bottom = bottom
                pages = append_source_page(output, "".join(content),
                    source.width, source.height, pymupdf.Rect(left, top, right, source.height - 42), css, archive)
                self.last_page_map.append({"source_page": source.page_num, "output_pages": [p + 1 for p in pages]})
                toc.append([1, f"Source page {source.page_num}", pages[0] + 1])
                if preserve_numbers:
                    for continuation, index in enumerate(pages):
                        label = f"Source page {source.page_num}"
                        if continuation:
                            label += f" - continued {continuation + 1}"
                        output[index].insert_textbox(pymupdf.Rect(left, source.height - 30, right, source.height - 12),
                                                     label, fontsize=8, align=1)
            output.set_toc(toc)
            output.save(str(out_file))
        return out_file
