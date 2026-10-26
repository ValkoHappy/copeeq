"""DocModel -> .docx. Deterministic: the same input always gives the same document."""

from collections.abc import Mapping
from dataclasses import replace
from io import BytesIO
from itertools import count
from typing import Any

import docx
from docx.document import Document as DocxDocument
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.oxml import serialize_part_xml
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.section import Section, _Footer, _Header
from docx.shared import Mm, Pt
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image

from foto2word.domain.document import (
    Block,
    Document,
    FontFace,
    Footnote,
    FootnoteParagraph,
    Orientation,
    PageGeometry,
    PageNumbers,
    SectionStart,
    SpacingRule,
)
from foto2word.domain.extras import NO_EXTRAS, RenderExtras
from foto2word.domain.profile import (
    Margins,
    PageSetup,
    Profile,
    RenderMode,
)
from foto2word.infrastructure.rendering.blocks import (
    BlockRenderer,
    default_registry,
    drop_needless_separators,
    hang_old_style_drawings,
)
from foto2word.infrastructure.rendering.formatting import (
    WORD_ALIGNMENT,
    RenderContext,
    set_font,
    set_frame,
)


class _Margin:
    """A header or footer as a place to write blocks; it starts with one paragraph, which is
    reused while it is empty."""

    def __init__(self, part: _Header | _Footer, page: PageSetup) -> None:
        self._part = part
        self._width = Mm(page.content_width_mm)
        self._fresh = not part.paragraphs[0].runs  # the page number may already be there

    def add_paragraph(self) -> Paragraph:
        if self._fresh:
            self._fresh = False
            first: Paragraph = self._part.paragraphs[0]
            return first
        return self._part.add_paragraph()

    def add_table(self, rows: int, cols: int) -> Table:
        table = self._part.add_table(rows, cols, self._width)
        if self._fresh:  # the part starts with the table; its own paragraph comes after it
            self._part.paragraphs[0]._p.addprevious(table._tbl)
        return table


_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def _finish_stories(output: DocxDocument) -> None:
    """The body, headers and footers lose separators they do not need, and their pictures are
    numbered once across all of them: a header picture numbered like one in the body makes
    Word call the file corrupted."""
    drawing_ids = count(1)
    for part in output.part.package.iter_parts():
        root = getattr(part, "_element", None)
        if root is not None and root.tag in (qn("w:document"), qn("w:hdr"), qn("w:ftr")):
            drop_needless_separators(root)
            for drawing in root.iter(f"{{{_WP_NS}}}docPr"):
                drawing.set("id", str(next(drawing_ids)))


class DocxRenderer:
    def __init__(self, registry: Mapping[type, BlockRenderer[Any]] | None = None) -> None:
        self._registry = registry or default_registry()

    def render(
        self,
        document: Document,
        profile: Profile,
        mode: RenderMode,
        extras: RenderExtras = NO_EXTRAS,
    ) -> bytes:
        output = docx.Document()
        if mode is RenderMode.FAITHFUL and document.font:  # the typeface seen on the photo
            profile = profile.model_copy(update={"styles": profile.styles.with_font(document.font)})
        page = self._page(document, profile, mode)
        self._setup_page(output, page, document.orientation)
        if mode is RenderMode.FAITHFUL and document.page is not None:
            _set_page_extras(output.sections[0], document.page)
        self._setup_default_font(output, profile)
        if mode is RenderMode.FAITHFUL:
            _set_compat(output, document)
        if mode is RenderMode.FAITHFUL and document.page_background:
            _set_page_background(output, document.page_background)
        if mode is RenderMode.FAITHFUL and document.spacing_rule is SpacingRule.SUM:
            self._add_up_spacing(output)
        if document.page_numbers is not None:
            self._page_numbers(output, document.page_numbers, profile)
        ctx = RenderContext(output, profile, mode, extras, page)
        self._render_blocks(document.blocks, ctx)
        if mode is RenderMode.FAITHFUL:
            hang_old_style_drawings(output.paragraphs)
        section = output.sections[0]
        first = section.different_first_page_header_footer  # a title page without a number
        header = section.first_page_header if first else section.header
        footer = section.first_page_footer if first else section.footer
        for blocks, part in ((document.header, header), (document.footer, footer)):
            if blocks:
                margin = RenderContext(_Margin(part, page), profile, mode, extras, page)
                self._render_blocks(blocks, margin)
        if extras.appendix:
            self._appendix(ctx, extras)
        if mode is RenderMode.FAITHFUL and document.fonts:
            _add_font_faces(output, document.fonts)
        if mode is RenderMode.FAITHFUL and document.footnotes:
            self._add_footnotes(output, document.footnotes, ctx)
        _finish_stories(output)
        buffer = BytesIO()
        output.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _page_numbers(output: DocxDocument, numbers: PageNumbers, profile: Profile) -> None:
        section = output.sections[0]
        part = section.header if numbers.position == "top" else section.footer
        if not numbers.first_page:
            section.different_first_page_header_footer = True
        paragraph = part.paragraphs[0]
        paragraph.alignment = WORD_ALIGNMENT[numbers.align]
        if numbers.frame:  # in its frame, as the original's: no line of the margin
            set_frame(paragraph, numbers.frame)
        layout = numbers.layout
        if layout is not None:  # the original's spacing lifts the number off the page's edge
            fmt = paragraph.paragraph_format
            fmt.space_before, fmt.space_after = (
                Pt(layout.space_before_pt or 0),
                Pt(layout.space_after_pt or 0),
            )
            if layout.line_spacing:
                fmt.line_spacing = layout.line_spacing
        run = paragraph.add_run()
        set_font(run, numbers.font or profile.styles.body.font)
        run.font.size = Pt(numbers.size_pt or profile.styles.body.size_pt)
        for kind, code in (("begin", None), (None, " PAGE "), ("separate", None), ("end", None)):
            if code is not None:
                instruction = OxmlElement("w:instrText")
                instruction.set(qn("xml:space"), "preserve")
                instruction.text = code
                run._r.append(instruction)
            else:
                char = OxmlElement("w:fldChar")
                char.set(qn("w:fldCharType"), str(kind))
                run._r.append(char)

    @staticmethod
    def _add_footnotes(
        output: DocxDocument, footnotes: tuple[Footnote, ...], ctx: RenderContext
    ) -> None:
        """The notes part, as Word writes it: two separators, then the notes. Their paragraphs
        are made in the body with the usual formatting and moved over."""
        notes = parse_xml(_FOOTNOTES_HEAD)
        style = ctx.profile.styles.body
        for note in footnotes:
            element = OxmlElement("w:footnote")
            element.set(qn("w:id"), str(note.id))
            for source in note.paragraphs or (FootnoteParagraph(),):
                paragraph = ctx.add_paragraph(ctx.styled(style, source.layout), source.align)
                ctx.write_runs(paragraph, source.runs, style)
                element.append(paragraph._p)  # moves it out of the body
            notes.append(element)
        part = Part(
            PackURI("/word/footnotes.xml"), _FOOTNOTES_TYPE, serialize_part_xml(notes),
            output.part.package,
        )  # fmt: skip
        output.part.relate_to(part, RT.FOOTNOTES)
        settings = output.settings.element
        if settings.find(qn("w:footnotePr")) is None:
            properties = parse_xml(_FOOTNOTE_PROPERTIES)
            compat = settings.find(qn("w:compat"))
            if compat is not None:
                compat.addprevious(properties)
            else:
                settings.append(properties)

    @staticmethod
    def _add_up_spacing(output: DocxDocument) -> None:
        """Like the original: spacing after and before neighbouring paragraphs adds up."""
        settings = output.settings.element
        compat = settings.find(qn("w:compat"))
        if compat is None:
            compat = OxmlElement("w:compat")
            settings.append(compat)
        if compat.find(qn("w:doNotUseHTMLParagraphAutoSpacing")) is None:
            compat.insert(0, OxmlElement("w:doNotUseHTMLParagraphAutoSpacing"))

    def _render_blocks(self, blocks: tuple[Block, ...], ctx: RenderContext) -> None:
        for block in blocks:
            renderer = self._registry.get(type(block))
            if renderer is None:
                raise TypeError(f"No renderer registered for block kind '{block.kind}'")
            if block.section is not None and ctx.faithful and isinstance(ctx.docx, DocxDocument):
                _start_section(ctx.docx, block.section, first=block is blocks[0])
                if block.section.page is not None:  # widths and tabs follow the section's page
                    ctx = replace(ctx, page=_page_setup(block.section.page))
            elif block.page_break_before:
                _new_page(ctx)
            elif block.column_break_before and ctx.faithful:
                breaker = _new_column(ctx)
                renderer.render(block, ctx)
                _break_inside(breaker)
                continue
            renderer.render(block, ctx)

    @staticmethod
    def _appendix(ctx: RenderContext, extras: RenderExtras) -> None:
        """Photos of the original at the end, each on its own page, scaled to fit."""
        page = ctx.page or ctx.profile.page
        max_w = page.content_width_mm
        max_h = page.height_mm - page.margins.top_mm - page.margins.bottom_mm - 20
        title = ctx.add_paragraph(ctx.profile.styles.subtitle, first_line_indent_mm=0)
        title.paragraph_format.page_break_before = True
        ctx.write_text(title, "Приложение. Фото оригинала", ctx.profile.styles.subtitle)
        for index, photo in enumerate(extras.appendix):
            with Image.open(BytesIO(photo.data)) as image:
                ratio = image.height / image.width
            width = min(max_w, max_h / ratio)
            paragraph = ctx.add_paragraph(ctx.profile.styles.line, first_line_indent_mm=0)
            paragraph.paragraph_format.page_break_before = index > 0
            paragraph.add_run().add_picture(BytesIO(photo.data), width=Mm(width))

    @staticmethod
    def _page(document: Document, profile: Profile, mode: RenderMode) -> PageSetup:
        source = document.page
        if mode is not RenderMode.FAITHFUL or source is None:
            return profile.page
        margins = Margins(
            top_mm=source.top_mm,
            bottom_mm=source.bottom_mm,
            left_mm=source.left_mm,
            right_mm=source.right_mm,
        )
        portrait = sorted((source.width_mm, source.height_mm))
        return PageSetup(width_mm=portrait[0], height_mm=portrait[1], margins=margins)

    @staticmethod
    def _setup_page(output: DocxDocument, page: PageSetup, orientation: Orientation) -> None:
        width, height = page.width_mm, page.height_mm
        section = output.sections[0]
        if orientation is Orientation.LANDSCAPE:
            width, height = height, width
            section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = Mm(width), Mm(height)
        section.top_margin = Mm(page.margins.top_mm)
        section.bottom_margin = Mm(page.margins.bottom_mm)
        section.left_margin = Mm(page.margins.left_mm)
        section.right_margin = Mm(page.margins.right_mm)

    @staticmethod
    def _setup_default_font(output: DocxDocument, profile: Profile) -> None:
        body = profile.styles.body
        normal = output.styles["Normal"]
        normal.font.name = body.font
        normal.font.size = Pt(body.size_pt)
        fonts = output.styles.element.find(
            f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:rFonts')}"
        )
        if fonts is not None:  # named, not the theme's: a theme face would win over a run's own
            fonts.attrib.clear()
            for side in ("ascii", "hAnsi", "eastAsia", "cs"):
                fonts.set(qn(f"w:{side}"), body.font)


def _page_setup(page: PageGeometry) -> PageSetup:
    """The page as laid out: a landscape section keeps its width as the long side."""
    margins = Margins(
        top_mm=page.top_mm, bottom_mm=page.bottom_mm, left_mm=page.left_mm, right_mm=page.right_mm
    )
    return PageSetup(width_mm=page.width_mm, height_mm=page.height_mm, margins=margins)


def _start_section(output: DocxDocument, start: SectionStart, *, first: bool) -> None:
    """A section break before the block, with the section's page and columns. Word keeps the
    break in the last paragraph of the section before; python-docx adds a paragraph for it,
    which is merged into that one when it is a paragraph."""
    if first:
        section = output.sections[-1]
    else:
        section = output.add_section(
            WD_SECTION.NEW_PAGE if start.new_page else WD_SECTION.CONTINUOUS
        )
        holder = output.element.body.findall(qn("w:p"))[-1]
        previous = holder.getprevious()
        if previous is not None and previous.tag == qn("w:p") and previous.find(_SECT) is None:
            previous.get_or_add_pPr().append(holder.pPr.find(qn("w:sectPr")))
            holder.getparent().remove(holder)
    if start.page is not None:
        landscape = start.page.width_mm > start.page.height_mm
        section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Mm(start.page.width_mm), Mm(start.page.height_mm)
        section.top_margin, section.bottom_margin = Mm(start.page.top_mm), Mm(start.page.bottom_mm)
        section.left_margin, section.right_margin = Mm(start.page.left_mm), Mm(start.page.right_mm)
        _set_page_extras(section, start.page)
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    for old in cols.findall(qn("w:col")):  # a new section copies the previous one's columns
        cols.remove(old)
    cols.attrib.pop(qn("w:equalWidth"), None)
    if start.columns > 1:
        cols.set(qn("w:num"), str(start.columns))
        cols.set(qn("w:space"), str(round(start.column_gap_mm * 1440 / 25.4)))
        if start.column_widths_mm:  # columns of their own widths
            cols.set(qn("w:equalWidth"), "0")
            for width, gap in start.column_widths_mm:
                col = OxmlElement("w:col")
                col.set(qn("w:w"), str(round(width * 1440 / 25.4)))
                col.set(qn("w:space"), str(round(gap * 1440 / 25.4)))
                cols.append(col)
    else:
        for name in ("w:num", "w:space"):
            cols.attrib.pop(qn(name), None)


_SECT = f"{qn('w:pPr')}/{qn('w:sectPr')}"


_MODERN_WORD = 15
_W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_FOOTNOTES_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
_FOOTNOTES_HEAD = (
    f"<w:footnotes {_W_NS}>"
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" '
    'w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" '
    'w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p>'
    "</w:footnote></w:footnotes>"
)
_FOOTNOTE_PROPERTIES = (
    f'<w:footnotePr {_W_NS}><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>'
)
_TWIPS_PER_PT = 20
"""Word 2013 and later: what a photographed document was most likely typed in."""


def _set_compat(output: DocxDocument, document: Document) -> None:
    """Lay the text out as the Word version of the original does: its mode and, when known, its
    own switches only (ours from the template change tables and spacing in older modes)."""
    settings = output.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    if document.compat_switches is not None:
        for child in list(compat):
            compat.remove(child)
        for name in document.compat_switches:
            compat.append(OxmlElement(f"w:{name}"))
        for name, value in document.compat_settings or ():
            compat.append(_compat_setting(name, value))
    mode = compat.find(f"{qn('w:compatSetting')}[@{qn('w:name')}='compatibilityMode']")
    if mode is None:
        mode = _compat_setting("compatibilityMode", "")
        compat.append(mode)
    mode.set(qn("w:val"), str(document.compat_mode or _MODERN_WORD))
    step = settings.find(qn("w:defaultTabStop"))
    if document.default_tab_pt is not None and step is not None:
        step.set(qn("w:val"), str(round(document.default_tab_pt * _TWIPS_PER_PT)))
    lang = output.styles.element.find(
        f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:lang')}"
    )
    if document.language and lang is not None:  # hyphenated by the rules of its language
        lang.set(qn("w:val"), document.language)
    for name, value in document.hyphenation:  # Word's automatic hyphenation, as the original's
        later = _AFTER_BACKGROUND_SHAPE[_AFTER_BACKGROUND_SHAPE.index(f"w:{name}") + 1 :]
        settings.insert_element_before(OxmlElement(f"w:{name}", {qn("w:val"): value}), *later)


def _set_page_background(output: DocxDocument, colour: str) -> None:
    """The page colour, shown and printed (w:displayBackgroundShape)."""
    background = OxmlElement("w:background")
    background.set(qn("w:color"), colour)
    output.element.insert(0, background)
    settings = output.settings.element
    if settings.find(qn("w:displayBackgroundShape")) is None:
        shown = OxmlElement("w:displayBackgroundShape")
        settings.insert_element_before(shown, *_AFTER_BACKGROUND_SHAPE)


_AFTER_BACKGROUND_SHAPE = (
    "w:doNotTrackMoves", "w:doNotTrackFormatting", "w:documentProtection",
    "w:autoFormatOverride", "w:styleLockTheme", "w:styleLockQFSet", "w:defaultTabStop",
    "w:autoHyphenation", "w:consecutiveHyphenLimit", "w:hyphenationZone", "w:doNotHyphenateCaps",
    "w:showEnvelope", "w:summaryLength", "w:clickAndTypeStyle", "w:defaultTableStyle",
    "w:evenAndOddHeaders", "w:bookFoldRevPrinting", "w:bookFoldPrinting",
    "w:bookFoldPrintingSheets", "w:drawingGridHorizontalSpacing", "w:drawingGridVerticalSpacing",
    "w:displayHorizontalDrawingGridEvery", "w:displayVerticalDrawingGridEvery",
    "w:doNotUseMarginsForDrawingGridOrigin", "w:drawingGridHorizontalOrigin",
    "w:drawingGridVerticalOrigin", "w:doNotShadeFormData", "w:noPunctuationKerning",
    "w:characterSpacingControl", "w:printTwoOnOne", "w:strictFirstAndLastChars",
    "w:noLineBreaksAfter", "w:noLineBreaksBefore", "w:savePreviewPicture",
    "w:doNotValidateAgainstSchema", "w:saveInvalidXml", "w:ignoreMixedContent",
    "w:alwaysShowPlaceholderText", "w:doNotDemarcateInvalidXml", "w:saveXmlDataOnly",
    "w:useXSLTWhenSaving", "w:saveThroughXslt", "w:showXMLTags", "w:alwaysMergeEmptyNamespace",
    "w:updateFields", "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat",
    "w:docVars", "w:rsids", "m:mathPr", "w:attachedSchema", "w:themeFontLang",
    "w:clrSchemeMapping", "w:doNotIncludeSubdocsInStats", "w:doNotAutoCompressPictures",
    "w:forceUpgrade", "w:captions", "w:readModeInkLockDown", "w:smartTagType",
    "sl:schemaLibrary", "w:shapeDefaults", "w:doNotEmbedSmartTags", "w:decimalSymbol",
    "w:listSeparator",
)  # fmt: skip
"""What follows w:displayBackgroundShape in w:settings, in the schema's order."""


def _add_font_faces(output: DocxDocument, faces: tuple[FontFace, ...]) -> None:
    """The original's typeface descriptions our template lacks, so Word substitutes alike."""
    part = next(
        (p for p in output.part.package.iter_parts() if str(p.partname) == "/word/fontTable.xml"),
        None,
    )
    if part is None:
        return
    table = parse_xml(part.blob)
    known = {font.get(qn("w:name")) for font in table.findall(qn("w:font"))}
    for face in faces:
        if face.name in known:
            continue
        font = OxmlElement("w:font")
        table.append(font)
        font.set(qn("w:name"), face.name)
        for tag, value in (
            ("altName", face.alt_name), ("panose1", face.panose), ("charset", face.charset),
            ("family", face.family), ("pitch", face.pitch),
        ):  # fmt: skip
            if value is not None:
                child = OxmlElement(f"w:{tag}")
                child.set(qn("w:val"), value)
                font.append(child)
            if tag == "family" and face.not_true_type:  # the schema puts it between the two
                font.append(OxmlElement("w:notTrueType"))
        if face.signature:
            sig = OxmlElement("w:sig")
            for name, value in face.signature:
                sig.set(qn(f"w:{name}"), value)
            font.append(sig)
    part._blob = serialize_part_xml(table)


def _compat_setting(name: str, value: str) -> BaseOxmlElement:
    return OxmlElement(
        "w:compatSetting",
        {
            qn("w:name"): name,
            qn("w:uri"): "http://schemas.microsoft.com/office/word",
            qn("w:val"): value,
        },
    )


def _set_doc_grid(sect_pr: BaseOxmlElement, grid: tuple[tuple[str, str], ...] | None) -> None:
    """The original's grid of lines, last in the section as Word keeps it; none: as it is."""
    if grid is None:
        return
    for old in sect_pr.findall(qn("w:docGrid")):
        sect_pr.remove(old)
    sect_pr.append(OxmlElement("w:docGrid", {qn(f"w:{name}"): value for name, value in grid}))


def _set_exact_margins(section: Section, exact: tuple[bool, bool]) -> None:
    """Top and bottom margins held exactly are written negative: the header and footer do not
    push the text then."""
    margins = section._sectPr.find(qn("w:pgMar"))
    for edge, held in zip(("top", "bottom"), exact, strict=True):
        if held and margins is not None:
            margins.set(qn(f"w:{edge}"), str(-abs(int(margins.get(qn(f"w:{edge}")) or 0))))


def _set_page_extras(section: Section, page: PageGeometry) -> None:
    """Header and footer distances, the binding room, the frame around the page and where page
    numbers start."""
    section.gutter = Mm(page.gutter_mm)
    _set_exact_margins(section, page.exact)
    if page.header_mm is not None:
        section.header_distance = Mm(page.header_mm)
    if page.footer_mm is not None:
        section.footer_distance = Mm(page.footer_mm)
    sect_pr = section._sectPr
    for old in sect_pr.findall(qn("w:pgBorders")):
        sect_pr.remove(old)
    if page.borders:  # a frame around the page, right after the margins as Word keeps it
        frame = OxmlElement(
            "w:pgBorders", {qn("w:offsetFrom"): "text" if page.borders_from_text else "page"}
        )
        for side in ("top", "left", "bottom", "right"):
            line = dict(page.borders).get(side)
            if line is not None:
                frame.append(
                    OxmlElement(
                        f"w:{side}",
                        {
                            qn("w:val"): line.style,
                            qn("w:sz"): str(line.size),
                            qn("w:space"): str(line.space_pt),
                            qn("w:color"): line.color or "auto",
                        },
                    )
                )
        margins = sect_pr.find(qn("w:pgMar"))
        if margins is not None:
            margins.addnext(frame)
        else:
            sect_pr.append(frame)
    _set_doc_grid(sect_pr, page.doc_grid)
    for old in sect_pr.findall(qn("w:pgNumType")):
        sect_pr.remove(old)
    if page.number_start is not None:  # numbered on from the original's first number
        numbering = OxmlElement("w:pgNumType", {qn("w:start"): str(page.number_start)})
        columns = sect_pr.find(qn("w:cols"))
        if columns is not None:  # Word keeps it before the columns
            columns.addprevious(numbering)
        else:
            sect_pr.append(numbering)


def _new_column(ctx: RenderContext) -> Paragraph:
    """A 1-pt paragraph whose break sends what follows to the next column."""
    paragraph = ctx.docx.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = fmt.space_after = Pt(0)
    fmt.line_spacing = Pt(1)
    run = paragraph.add_run()
    run.font.size = Pt(1)
    run.add_break(WD_BREAK.COLUMN)
    return paragraph


def _break_inside(breaker: Paragraph) -> None:
    """The break moves to the start of the block's own first paragraph, as in the original:
    Word sets a paragraph that starts with a column break wholly in the next column, its
    spacing before included (9144a589)."""
    following = breaker._p.getnext()
    if following is None or following.tag != qn("w:p"):
        return  # a table: the 1-pt paragraph stays
    run = OxmlElement("w:r")
    brk = OxmlElement("w:br")
    brk.set(qn("w:type"), "column")
    run.append(brk)
    following.insert(1 if following.find(qn("w:pPr")) is not None else 0, run)
    breaker._p.getparent().remove(breaker._p)


def _new_page(ctx: RenderContext) -> None:
    """A 1-pt paragraph that starts a new page, so the block keeps its own first line."""
    paragraph = ctx.docx.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.page_break_before = True
    fmt.space_before = fmt.space_after = Pt(0)
    fmt.line_spacing = Pt(1)
    paragraph.add_run().font.size = Pt(1)
