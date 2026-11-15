"""Export pilot.json with the bundled document runtime."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.document.docx_builder import DOCXBuilder
from app.document.document_model import DocumentModel
from app.document.page_model import PageModel
from app.document.paragraph_model import ParagraphModel

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
document = DocumentModel(Path(data["source"]), "Local translation pilot", 0, len(data["pages"]))
for number in data["pages"]:
    page = PageModel(number, 612, 792)
    for u in data["units"]:
        if u["page"] == number:
            page.paragraphs.append(ParagraphModel(id=u["id"], text=u["source"], translated_text=u["translation"], is_heading=u["is_heading"], status=u["status"]))
    document.pages.append(page)
provider = data.get("provider", "local")
output = path.with_name(f"{provider}_translation_review.docx")
label = "ক্লাউড অনুবাদ" if provider == "cloud" else "স্থানীয় মডেলের অনুবাদ"
print(DOCXBuilder().build_docx(document, output, "পার্থক্য ও পুনরাবৃত্তি\n" + label, reading_copy=True))
