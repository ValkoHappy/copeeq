from collections.abc import Sequence
from io import BytesIO

from PIL import Image

from foto2word.application.convert import ConversionOptions, ConvertDocument
from foto2word.application.ports import Provenance, Understanding, UnderstandingContext
from foto2word.domain.document import BoundingBox, Document
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine
from foto2word.domain.profile import RenderMode
from foto2word.infrastructure.images import PillowImageLoader
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository
from foto2word.infrastructure.rendering.docx_renderer import DocxRenderer


def _text_pdf(text: str) -> bytes:
    """A one-page A4 PDF with a real text layer."""
    stream = f"BT /F1 14 Tf 72 760 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def _scan_pdf() -> bytes:
    out = BytesIO()
    Image.new("RGB", (600, 850), "white").save(out, format="PDF")
    return out.getvalue()


def test_a_pdf_page_brings_its_text_layer_and_a_scan_does_not() -> None:
    loader = PillowImageLoader(max_side_px=1000)

    (page,) = loader.load_document(_text_pdf("Statement of the applicant, form 12"), "a.pdf")
    (scan,) = loader.load_document(_scan_pdf(), "scan.pdf")

    assert page.media_type == "image/jpeg"
    assert [line.text for line in page.lines] == ["Statement of the applicant, form 12"]
    assert page.lines[0].box.y0 < 0.15
    assert scan.lines == ()
    with Image.open(BytesIO(page.data)) as image:
        assert max(image.size) == 1000


class _Vision:
    def __init__(self, document: Document) -> None:
        self.document = document

    def understand(
        self, pages: Sequence[PageImage], context: UnderstandingContext
    ) -> Understanding:
        return Understanding(self.document, Provenance("fake", "fake-1", "understand.v1"))


class _Recorder:
    """Plays the OCR, the flattener and the layout estimator, and remembers what it was given."""

    def __init__(self) -> None:
        self.read: list[str] = []
        self.flattened: list[str] = []
        self.lines: list[TextLine] = []

    def read_lines(self, pages: Sequence[PageImage]) -> list[TextLine]:
        self.read += [p.source_name for p in pages]
        box = BoundingBox(x0=0.1, y0=0.1, x1=0.9, y1=0.12)
        return [TextLine(page=1, text="from the photo", box=box)]

    def rectify(self, page: PageImage) -> PageImage:
        self.flattened.append(page.source_name)
        return page

    def estimate(
        self, document: Document, pages: Sequence[PageImage], lines: Sequence[TextLine] = ()
    ) -> Document:
        self.lines = list(lines)
        return document


def test_a_pdf_page_is_neither_flattened_nor_read_by_ocr(
    act: Document, profiles: YamlProfileRepository
) -> None:
    recorder = _Recorder()
    box = BoundingBox(x0=0.1, y0=0.2, x1=0.9, y1=0.22)
    pdf_page = PageImage(
        b"jpeg", "image/jpeg", "a.pdf #1", (TextLine(page=1, text="exact", box=box),)
    )
    photo = PageImage(b"jpeg", "image/jpeg", "photo.jpg")
    converter = ConvertDocument(
        _Vision(act), DocxRenderer(), profiles, layout=recorder, lines=recorder, rectifier=recorder
    )

    converter.analyze([pdf_page, photo], ConversionOptions(mode=RenderMode.FAITHFUL))

    assert recorder.flattened == ["photo.jpg"]
    assert recorder.read == ["photo.jpg"]
    assert [(line.page, line.text) for line in recorder.lines] == [
        (1, "exact"),
        (2, "from the photo"),
    ]
