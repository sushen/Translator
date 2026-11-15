"""Readable pagination within a source page, with explicit continuation mapping."""
import io
import pymupdf


def append_source_page(output, markup, width, height, frame, css, archive):
    """Append one or more pages without scaling fonts or mixing source pages."""
    stream = io.BytesIO()
    story = pymupdf.Story(html=markup or "<p></p>", user_css=css, archive=archive)
    writer = pymupdf.DocumentWriter(stream)
    count = 0
    try:
        more = True
        while more:
            device = writer.begin_page(pymupdf.Rect(0, 0, width, height))
            more, filled = story.place(frame)
            if more and pymupdf.Rect(filled).height <= 0:
                raise ValueError("Content cannot fit the page width. Resize oversized images or text.")
            story.draw(device)
            writer.end_page()
            count += 1
            if count > 1000:
                raise ValueError("Page content exceeds the continuation limit.")
    finally:
        writer.close()
    first = len(output)
    with pymupdf.open(stream=stream.getvalue(), filetype="pdf") as part:
        output.insert_pdf(part)
    return list(range(first, len(output)))
