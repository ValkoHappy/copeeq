"""Pictures written into a paragraph: at the original's size, cropped as in the original,
numbered once across the whole document."""

from io import BytesIO

from docx.image.exceptions import UnrecognizedImageError
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.shape import CT_Inline
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.parts.image import ImagePart
from docx.shape import InlineShape
from docx.shared import Mm
from docx.text.paragraph import Paragraph
from docx.text.run import Run as DocxRun

_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def add_picture(
    paragraph: Paragraph,
    run: DocxRun,
    data: bytes,
    width_mm: float | None,
    height_mm: float | None,
) -> InlineShape | None:
    """The picture in the run, at the original's size. One python-docx cannot read (an EMF or
    WMF drawing, a JPEG with a Photoshop header) goes in as its own bytes: Word shows it as
    it was. None when neither works."""
    width = Mm(width_mm) if width_mm else None
    height = Mm(height_mm) if height_mm else None
    try:
        return run.add_picture(BytesIO(data), width=width, height=height)
    except UnrecognizedImageError:
        kind = _picture_kind(data)
        if kind is None or width is None or height is None:
            return None
    extension, content_type = kind
    part = paragraph.part
    name = part.package.next_partname(f"/word/media/image%d.{extension}")
    rel_id = part.relate_to(ImagePart(name, content_type, data), RELATIONSHIP_TYPE.IMAGE)
    inline = CT_Inline.new_pic_inline(
        next_drawing_id(paragraph), rel_id, f"image.{extension}", width, height
    )
    run._r.add_drawing(inline)
    return InlineShape(inline)


def set_effect(inline: BaseOxmlElement, sides: tuple[int, int, int, int]) -> None:
    """Room around the picture for its shadow or glow (wp:effectExtent), right after its size:
    Word makes the line that much taller."""
    for old in inline.findall(qn("wp:effectExtent")):
        inline.remove(old)
    extent = OxmlElement(
        "wp:effectExtent",
        {"l": str(sides[0]), "t": str(sides[1]), "r": str(sides[2]), "b": str(sides[3])},
    )
    inline.find(qn("wp:extent")).addnext(extent)


def set_crop(inline: BaseOxmlElement, crop: tuple[float, float, float, float]) -> None:
    """Only the cropped part of the picture shows, at the size given: Word's a:srcRect."""
    fill = next(inline.iter(qn("pic:blipFill")), None)
    blip = fill.find(qn("a:blip")) if fill is not None else None
    if fill is None or blip is None:
        return
    for old in fill.findall(qn("a:srcRect")):
        fill.remove(old)
    sides = dict(zip(("l", "t", "r", "b"), crop, strict=True))
    blip.addnext(OxmlElement("a:srcRect", {k: str(round(v * 100_000)) for k, v in sides.items()}))


def _picture_kind(data: bytes) -> tuple[str, str] | None:
    """File extension and content type of a picture by its first bytes."""
    if data.startswith(b"\xff\xd8"):
        return "jpeg", "image/jpeg"
    if data.startswith((b"\xd7\xcd\xc6\x9a", b"\x01\x00\x09\x00", b"\x02\x00\x09\x00")):
        return "wmf", "image/x-wmf"
    if data.startswith(b"\x01\x00\x00\x00") and data[40:44] == b" EMF":
        return "emf", "image/x-emf"
    return None


def next_drawing_id(paragraph: Paragraph) -> int:
    """Drawing ids are unique across the body, headers and footers: Word calls a file with a
    repeated one corrupted."""
    ids = [0]
    for part in paragraph.part.package.iter_parts():
        root = getattr(part, "_element", None)
        if root is not None:
            ids += [int(d.get("id") or 0) for d in root.iter(f"{{{_WP_NS}}}docPr")]
    return max(ids) + 1
