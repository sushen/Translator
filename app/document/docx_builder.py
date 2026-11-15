"""Editable Unicode Bangla export from the same document used for PDF export."""
from pathlib import Path


class DOCXBuilder:
    def build_docx(self, document_model, output_path: Path, title="Bangla translation review", include_source=False, reading_copy=False):
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        doc = Document()
        section = doc.sections[0]
        section.page_width, section.page_height = Inches(8.5), Inches(11)
        section.top_margin = section.bottom_margin = Inches(0.8)
        section.left_margin = section.right_margin = Inches(0.85)
        for name in ("Normal", "Title", "Heading 1", "Heading 2"):
            style = doc.styles[name]
            family = "Noto Serif Bengali" if name == "Normal" else "Noto Sans Bengali"
            style.font.name = family
            style.font.color.rgb = RGBColor(0, 0, 0)
            fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
            for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                fonts.set(qn(f"w:{attr}"), family)
            lang = OxmlElement("w:lang")
            lang.set(qn("w:val"), "bn-BD")
            lang.set(qn("w:bidi"), "bn-BD")
            style.element.get_or_add_rPr().append(lang)
        normal = doc.styles["Normal"]
        normal.font.size = Pt(14)
        normal.paragraph_format.line_spacing = 1.5
        normal.paragraph_format.space_after = Pt(8)
        doc.add_paragraph(title, "Title")
        if not reading_copy:
            introduction = doc.add_paragraph("Machine translation draft for human review. Failed paragraphs are explicitly marked. Bengali fonts must be installed on the reviewing computer.")
            for run in introduction.runs:
                run.font.size = Pt(10)
        for page in document_model.pages:
            label = f"মূল পিডিএফের পৃষ্ঠা {page.page_num}" if reading_copy else f"Source PDF page {page.page_num}"
            doc.add_paragraph(label, "Heading 1")
            for para in page.paragraphs:
                if para.is_page_number:
                    continue
                if include_source:
                    doc.add_paragraph("English source", "Heading 2")
                    source = doc.add_paragraph(para.text)
                    for run in source.runs:
                        run.font.size = Pt(11)
                    doc.add_paragraph("Bangla draft", "Heading 2")
                text = para.current_translation
                if para.status == "failed" or not text:
                    doc.add_paragraph("এই অনুচ্ছেদের অনুবাদ সম্পন্ন হয়নি।" if reading_copy else "Translation unavailable for this paragraph")
                    if not reading_copy:
                        doc.add_paragraph(para.text)
                else:
                    doc.add_paragraph(text, "Heading 2" if para.is_heading else "Normal")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        return output_path
