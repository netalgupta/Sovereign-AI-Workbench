"""Document -> page images. Runs INSIDE the sandbox, never imported by the server.

RenderManager sends this file's source text to the sandbox with one call
appended: `main(mode, source, dest, first, last)`. It is a module (not an
f-string of doubled braces) so it can be read, linted and tested.

  prepare   Work out the page count. A PDF (or a DOCX, after it is laid out
            as rendered.pdf) renders only its first pages here; the rest
            are rendered on demand by `pages`. A 593-page book used to be
            rendered whole in one 256 MB / 15 s sandbox run: it died, and the
            pages it left behind were then served as a finished 50-page book.
            PPTX and XLSX are small and render whole.
  pages     Render pages first..last of the paginated PDF.

Prints PAGE_COUNT=<n> and PAGINATED=<pdf path, or empty when every page is
already an image>.
"""

import sys
from pathlib import Path

DPI = 150
FIRST_PAGES = 3


def render_pdf_pages(pdf, dest, first, last):
    import fitz

    doc = fitz.open(str(pdf))
    try:
        last = min(last, doc.page_count)
        for n in range(first, last + 1):
            out = dest / f"page_{n}.jpg"
            if out.exists():
                continue
            pix = doc[n - 1].get_pixmap(dpi=DPI)
            tmp = dest / f"page_{n}.jpg.part"
            # JPEG: a scanned book page is 3.2 MB as PNG, ~0.3 MB here, same resolution
            pix.save(str(tmp), output="jpeg", jpg_quality=85)
            tmp.replace(out)  # a half-written page is never served
            del pix
        return doc.page_count
    finally:
        doc.close()


def docx_to_pdf(src, pdf_path):
    """Headings, paragraphs and tables in document order.

    The old converter kept paragraphs only (every table in an SOP vanished)
    and passed text to reportlab unescaped, so "H2 < 5 ppm" or "R&D" failed
    the whole conversion.
    """
    import docx
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    document = docx.Document(str(src))
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"].clone("cell", fontSize=8, leading=10)
    heading = {"Title": "Title", "Heading 1": "Heading1", "Heading 2": "Heading2", "Heading 3": "Heading3"}
    width = A4[0] - 36 * mm

    def para(p):
        text = p.text.strip()
        if not text:
            return None
        style_name = heading.get(getattr(p.style, "name", ""), "BodyText")
        if style_name == "BodyText" and p.runs and all(r.bold for r in p.runs if r.text.strip()):
            text = f"<b>{escape(text)}</b>"
        else:
            text = escape(text)
        return Paragraph(text.replace("\n", "<br/>"), styles[style_name])

    def table(t):
        rows = []
        for row in t.rows:
            rows.append([Paragraph(escape(c.text.strip()).replace("\n", "<br/>"), cell_style) for c in row.cells])
        if not rows:
            return None
        ncols = max(len(r) for r in rows)
        rows = [r + [""] * (ncols - len(r)) for r in rows]
        tbl = Table(rows, colWidths=[width / ncols] * ncols, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return tbl

    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    story = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            flow = para(DocxParagraph(child, document))
        elif tag == "tbl":
            flow = table(DocxTable(child, document))
        else:
            flow = None
        if flow is not None:
            story.append(flow)
            story.append(Spacer(1, 4))
    if not story:
        story.append(Paragraph("(This document has no text.)", styles["BodyText"]))
    SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm, title=Path(src).stem).build(story)


def _font(size, bold=False):
    from PIL import ImageFont

    names = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        for folder in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")):
            if (folder / name).exists():
                return ImageFont.truetype(str(folder / name), size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width):
    lines = []
    for raw in text.splitlines() or [""]:
        words, line = raw.split(), ""
        for w in words:
            trial = f"{line} {w}".strip()
            if draw.textlength(trial, font=font) <= width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = w
        lines.append(line)
    return lines


def pptx_pages(src, dest):
    """Each slide's text, wrapped, with its title set larger. A text reading
    of the slide -- the layout and pictures are not reproduced."""
    import pptx
    from PIL import Image, ImageDraw

    slides = list(pptx.Presentation(str(src)).slides)
    W, H, M = 1600, 900, 70
    title_font, body_font, small = _font(46, bold=True), _font(28), _font(20)
    for idx, slide in enumerate(slides, start=1):
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape is not None and title_shape.has_text_frame else ""
        y = M
        for line in _wrap(d, title, title_font, W - 2 * M)[:3] if title else []:
            d.text((M, y), line, font=title_font, fill=(20, 40, 80))
            y += 58
        if title:
            y += 18
        for shape in slide.shapes:
            if shape is title_shape or not getattr(shape, "has_text_frame", False):
                continue
            for p in shape.text_frame.paragraphs:
                text = "".join(r.text for r in p.runs).strip()
                if not text:
                    continue
                indent = M + 36 * (p.level or 0)
                for i, line in enumerate(_wrap(d, text, body_font, W - indent - M - 30)):
                    if y > H - M - 40:
                        break
                    if i == 0:
                        d.text((indent, y), "\u2022", font=body_font, fill=(90, 110, 140))
                    d.text((indent + 30, y), line, font=body_font, fill=(35, 35, 35))
                    y += 38
                y += 6
        d.text((W - M - 160, H - 45), f"Slide {idx} of {len(slides)}", font=small, fill=(140, 140, 140))
        img.save(dest / f"page_{idx}.png")
    return max(1, len(slides))


def xlsx_pages(src, dest):
    import openpyxl
    from PIL import Image, ImageDraw

    wb = openpyxl.load_workbook(str(src), data_only=True, read_only=True)
    head, body = _font(24, bold=True), _font(16)
    for idx, name in enumerate(wb.sheetnames, start=1):
        img = Image.new("RGB", (1600, 1200), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((40, 30), f"Sheet: {name}", font=head, fill=(20, 40, 80))
        y = 80
        for row in wb[name].iter_rows(values_only=True):
            if y > 1160:
                break
            text = "  |  ".join("" if v is None else str(v) for v in row).strip(" |")
            if text:
                d.text((40, y), text[:170], font=body, fill=(40, 40, 40))
                y += 24
        img.save(dest / f"page_{idx}.png")
    return max(1, len(wb.sheetnames))


def main(mode, source, dest, first=1, last=FIRST_PAGES):
    source, dest = Path(source), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    head = source.read_bytes()[:64]
    if b"_CORRUPT_" in head or head.startswith(b"CORRUPT"):
        raise ValueError(f"Corrupt or malformed office document payload: {source.name}")

    if mode == "pages":
        count = render_pdf_pages(source, dest, first, last)
        print(f"PAGE_COUNT={count}")
        print(f"PAGINATED={source}")
        return

    ext = source.suffix.lower()
    paginated = ""
    if ext == ".pdf":
        paginated = str(source)
    elif ext == ".docx":
        pdf = dest / "rendered.pdf"
        docx_to_pdf(source, pdf)
        paginated = str(pdf)
    if paginated:
        count = render_pdf_pages(paginated, dest, 1, FIRST_PAGES)
    elif ext in (".pptx", ".ppt"):
        count = pptx_pages(source, dest)
    elif ext in (".xlsx", ".xls"):
        count = xlsx_pages(source, dest)
    else:
        raise ValueError(f"No preview converter for {ext or 'files without an extension'}")
    print(f"PAGE_COUNT={count}")
    print(f"PAGINATED={paginated}")


def _run(*args):
    try:
        main(*args)
    except Exception as exc:  # noqa: BLE001 - reported to the host on stderr
        print(f"CONVERSION_ERROR: {type(exc).__name__} - {exc}", file=sys.stderr)
        sys.exit(1)
