"""Render the same pilot text in two embedded Bengali fonts for visual review."""
import html
import json
import sys
from pathlib import Path
import pymupdf

root = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
provider = data.get("provider", "local")
for family in ((sys.argv[2].capitalize(),) if len(sys.argv) > 2 else ("Serif", "Sans")):
    fonts = root / "assets/fonts"
    body_font = f"Noto{family}Bengali-Regular.ttf"
    css = f"""@font-face {{font-family:Body;src:url({body_font});}}
@font-face {{font-family:Heading;src:url(NotoSansBengali-Regular.ttf);}}
body {{font-family:Body;font-size:14pt;line-height:1.6;color:#111;}}
h1,h2,h3 {{font-family:Heading;color:#000;}}
h1 {{font-size:21pt;}} h2 {{font-size:16pt;margin-top:22pt;}}
h3 {{font-size:14pt;}} p {{margin-bottom:10pt;}}
.note {{font-size:10pt;color:#555;}}
.source {{font-size:11pt;line-height:1.45;}}
"""
    successful = sum(u["status"] == "translated" for u in data["units"])
    label = "ক্লাউড অনুবাদ" if provider == "cloud" else "স্থানীয় মডেলের অনুবাদ"
    content = [f"<h1>পার্থক্য ও পুনরাবৃত্তি</h1><p class='note'>{label} | পরীক্ষামূলক খসড়া</p>"]
    for page in data["pages"]:
        bengali_page = str(page).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
        content.append(f"<h2>মূল পিডিএফের পৃষ্ঠা {bengali_page}</h2>")
        for unit in data["units"]:
            if unit["page"] != page:
                continue
            if unit["status"] != "translated":
                content.append("<p><b>এই অনুচ্ছেদের অনুবাদ সম্পন্ন হয়নি।</b></p>")
            else:
                tag = "h3" if unit["is_heading"] else "p"
                content.append(f"<{tag}>{html.escape(unit['translation'])}</{tag}>")
    story = pymupdf.Story(html="".join(content), user_css=css, archive=pymupdf.Archive(str(fonts)))
    output = path.with_name(f"{provider}_translation_{family.lower()}.pdf")
    box = pymupdf.Rect(0, 0, 612, 792)
    def rectangles(rect_num, filled):
        return box, pymupdf.Rect(54, 54, 558, 738), None
    with pymupdf.DocumentWriter(str(output)) as writer:
        story.write(writer, rectangles)
    with pymupdf.open(output) as doc:
        print(f"{output}: {len(doc)} pages")
        doc[0].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(path.with_name(f"preview_{family.lower()}.png"))
