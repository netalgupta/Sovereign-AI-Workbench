"""Drawing primitives: every shape a layout places goes through these.

Kept small and strict so layouts read as design decisions, not
python-pptx plumbing -- and so an unstyled default (a shadow, an outline,
a Calibri run) can never leak onto a slide.
"""

from __future__ import annotations

from lxml import etree
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from . import theme
from .theme import rgb

ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}
_WEIGHT_FONT = {
    "regular": theme.FONT,
    "semibold": theme.FONT_SEMIBOLD,
    "bold": theme.FONT,
    "light": theme.FONT_LIGHT,
}


def _set_alpha(fill, alpha: float) -> None:
    solid = fill._xPr.find(qn("a:solidFill"))
    if solid is None:
        return
    clr = solid[0]
    for old in clr.findall(qn("a:alpha")):
        clr.remove(old)
    el = etree.SubElement(clr, qn("a:alpha"))
    el.set("val", str(int(alpha * 100000)))


def rect(slide, x, y, w, h, fill: str | None, *, line: str | None = None, line_pt: float = 0.75,
         radius: float | None = None, alpha: float | None = None, shape=None):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    s.shadow.inherit = False
    if radius and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
        if alpha is not None:
            _set_alpha(s.fill, alpha)
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_pt)
    if s.has_text_frame:
        s.text_frame.text = ""
    return s


def oval(slide, x, y, d, fill: str, *, line: str | None = None, line_pt: float = 1.5):
    return rect(slide, x, y, d, d, fill, line=line, line_pt=line_pt, shape=MSO_SHAPE.OVAL)


def hline(slide, x1, y, x2, colour: str, weight_pt: float = 0.75):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y), Inches(x2), Inches(y))
    c.line.color.rgb = rgb(colour)
    c.line.width = Pt(weight_pt)
    return c


def vline(slide, x, y1, y2, colour: str, weight_pt: float = 0.75):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y1), Inches(x), Inches(y2))
    c.line.color.rgb = rgb(colour)
    c.line.width = Pt(weight_pt)
    return c


def text(slide, x, y, w, h, value, *, size: float, colour: str = theme.PALETTE.ink,
         weight: str = "regular", align: str = "left", anchor: str = "top",
         line_spacing: float = 1.18, caps: bool = False, tracking: float | None = None,
         shape=None):
    """A text box with no margins and no autosize, so geometry is exact.

    `value` may be a string or a list of runs [(text, {size, colour, weight})]
    for mixed styling on one line (a number and its unit).
    """
    box = shape or slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ANCHOR[anchor]
    runs = value if isinstance(value, list) else [(value, {})]
    p = tf.paragraphs[0]
    p.alignment = ALIGN[align]
    p.line_spacing = line_spacing
    for chunk, style in runs:
        r = p.add_run()
        r.text = (chunk.upper() if caps else chunk) if chunk is not None else ""
        f = r.font
        wt = style.get("weight", weight)
        f.name = _WEIGHT_FONT[wt]
        f.bold = wt == "bold"
        f.size = Pt(style.get("size", size))
        f.color.rgb = rgb(style.get("colour", colour))
        trk = style.get("tracking", tracking)
        if trk:
            r._r.get_or_add_rPr().set("spc", str(int(trk * 100)))
    return box


def paragraphs(slide, x, y, w, h, items: list[str], *, size: float, colour: str = theme.PALETTE.ink,
               gap_pt: float = 8, line_spacing: float = 1.18, weight: str = "regular"):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = line_spacing
        if i:
            p.space_before = Pt(gap_pt)
        r = p.add_run()
        r.text = item
        r.font.name = _WEIGHT_FONT[weight]
        r.font.size = Pt(size)
        r.font.color.rgb = rgb(colour)
    return box


def pill(slide, x, y, label: str, fg: str, bg: str, *, size: float = 10, h: float = 0.3):
    from .fit import text_width_pt

    w = text_width_pt(label.upper(), size, "semibold") / 72.0 + 0.32
    s = rect(slide, x, y, w, h, bg, radius=0.5)
    text(slide, x, y, w, h, label, size=size, colour=fg, weight="semibold", align="center",
         anchor="middle", caps=True, tracking=0.6)
    return w


def background(slide, colour: str):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(colour)
