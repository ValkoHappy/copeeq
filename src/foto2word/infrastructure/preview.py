"""Previewers: .docx -> PDF (by a real word processor) -> page images.

The preview must show the document as the user will see it, so a real layout engine
(Microsoft Word or LibreOffice) does the conversion; pypdfium2 rasterises the PDF.
"""

import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from abc import ABC, abstractmethod
from functools import cache
from io import BytesIO
from pathlib import Path

import pypdfium2

from foto2word.application.ports import Previewer
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.images import PageImage

_TIMEOUT_S = 120
_PDF_FORMAT = 17  # wdFormatPDF


class PreviewError(Foto2WordError):
    pass


def pdf_to_pages(pdf: bytes, dpi: int = 110, max_pages: int = 10) -> list[PageImage]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        pages = []
        for index in range(min(len(document), max_pages)):
            image = document[index].render(scale=dpi / 72).to_pil().convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            pages.append(PageImage(buffer.getvalue(), "image/jpeg", f"render-{index + 1}.jpg"))
        return pages
    finally:
        document.close()


class _FilePreviewer(ABC):
    """Template: write .docx to a temp dir, let a subclass convert it, read back the PDF."""

    def __init__(self, dpi: int = 110) -> None:
        self._dpi = dpi

    def preview(self, rendered: bytes) -> list[PageImage]:
        return pdf_to_pages(self.to_pdf(rendered), self._dpi)

    def to_pdf(self, rendered: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix="f2w-preview-") as tmp:
            source = Path(tmp) / "document.docx"
            source.write_bytes(rendered)
            target = Path(tmp) / "document.pdf"
            self._convert(source, target)
            if not target.is_file():
                raise PreviewError("The word processor did not produce a PDF")
            return target.read_bytes()

    @abstractmethod
    def _convert(self, source: Path, target: Path) -> None: ...


class LibreOfficePreviewer(_FilePreviewer):
    def __init__(self, executable: str, dpi: int = 110) -> None:
        super().__init__(dpi)
        self._executable = executable

    def _convert(self, source: Path, target: Path) -> None:
        command = [
            self._executable,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(target.parent),
            str(source),
        ]
        _run(command)


class WordPreviewer:
    """Microsoft Word through COM automation (Windows with Word installed), one Word kept open
    between documents: starting Word costs seconds on every page drawn.

    Word draws one document at a time. It starts afresh every so often (a long session once drew
    a page in another typeface), and before a document naming a typeface Windows lacks: the
    substitute Word picks for one document sticks for the rest of its session (measured).
    """

    def __init__(self, dpi: int = 110) -> None:
        self._dpi = dpi
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._answers: queue.Queue[str] = queue.Queue()
        self._folder = Path(tempfile.mkdtemp(prefix="f2w-word-"))
        self._count = 0
        self._fresh = True

    def preview(self, rendered: bytes) -> list[PageImage]:
        return pdf_to_pages(self.to_pdf(rendered), self._dpi)

    def to_pdf(self, rendered: bytes) -> bytes:
        with self._lock:
            restart = (self._count and self._count % _RESTART_EVERY == 0) or (
                not self._fresh and missing_fonts(rendered, installed_fonts())
            )
            if restart:
                self.close()
            if self._process is None or self._process.poll() is not None:
                self._start()
            assert self._process is not None
            assert self._process.stdin is not None
            self._count += 1
            self._fresh = False
            source = self._folder / f"d{self._count}.docx"
            target = self._folder / f"d{self._count}.pdf"
            source.write_bytes(rendered)
            try:
                self._process.stdin.write(f"{source}\t{target}\n")
                self._process.stdin.flush()
                self._answer("ok", _TIMEOUT_S)
                return target.read_bytes()
            finally:
                source.unlink(missing_ok=True)
                target.unlink(missing_ok=True)

    def close(self) -> None:
        if self._process is not None:
            process, self._process = self._process, None
            try:
                if process.stdin is not None:
                    process.stdin.close()  # the script quits Word when its input ends
                process.wait(timeout=_QUIT_TIMEOUT_S)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                _kill_automation_word()
        self._fresh = True

    def _start(self) -> None:
        self._process = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WORD_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert self._process.stdout is not None
        self._answers = queue.Queue()
        stdout, answers = self._process.stdout, self._answers

        def relay() -> None:
            for line in stdout:
                answers.put(line.strip())

        threading.Thread(target=relay, daemon=True).start()
        self._answer("ready", _TIMEOUT_S)

    def _answer(self, expected: str, timeout: float) -> None:
        try:
            line = self._answers.get(timeout=timeout)
        except queue.Empty:
            if self._process is not None:
                self._process.kill()
                self._process = None
            _kill_automation_word()  # a document hung Word: the next one gets a new Word
            raise PreviewError(f"Word did not answer in {timeout:.0f} s") from None
        if not line.startswith(expected):
            raise PreviewError(f"Word: {line[:200]}")


_WORD_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
[Console]::Out.WriteLine('ready'); [Console]::Out.Flush()
while ($null -ne ($line = [Console]::In.ReadLine())) {
  $src, $dst = $line.Split([char]9)
  try {
    $d = $w.Documents.Open($src, $false, $true)
    $d.ExportAsFixedFormat($dst, 17, $false, 0, 0, 1, 1, 0)
    $d.Close($false)
    [Console]::Out.WriteLine('ok')
  } catch {
    try { $d.Close($false) } catch {}
    [Console]::Out.WriteLine('err ' + ($_.Exception.Message -replace '\s+', ' '))
  }
  [Console]::Out.Flush()
}
$w.Quit()
"""
"""Opens each file read-only and exports it as it reads: no reviewers' comments or change marks
(ExportAsFixedFormat item 0). Windows PowerShell mangles double quotes in -Command: none here."""
_RESTART_EVERY = 60
_QUIT_TIMEOUT_S = 15


@cache
def installed_fonts() -> frozenset[str]:
    """Typeface families Windows has, lower-cased."""
    listed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Drawing; "
            "(New-Object System.Drawing.Text.InstalledFontCollection).Families | "
            "ForEach-Object { $_.Name }",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return frozenset(line.strip().lower() for line in listed.splitlines() if line.strip())


def missing_fonts(data: bytes, installed: frozenset[str]) -> set[str]:
    """Typefaces the Word file's text and styles use that Windows does not have. Styles a
    template defines but no text uses do not count: only the defaults and the styles the text
    refers to, with the styles they are based on."""
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        parts = {
            name: archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.startswith("word/")
            and name.endswith(".xml")
            and "fontTable" not in name
            and "stylesWith" not in name
        }
    except zipfile.BadZipFile:
        return set()
    styles = parts.pop("word/styles.xml", "")
    blocks = {
        match.group(1): match.group(0)
        for match in re.finditer(r'<w:style [^>]*w:styleId="([^"]+)".*?</w:style>', styles, re.S)
    }
    body = " ".join(parts.values())
    wanted = set(re.findall(r'<w:(?:pStyle|rStyle|tblStyle) w:val="([^"]+)"', body))
    wanted |= {sid for sid, block in blocks.items() if 'w:default="1"' in block.split(">", 1)[0]}
    used: list[str] = re.findall(r"<w:docDefaults>.*?</w:docDefaults>", styles, re.S)
    seen: set[str] = set()
    while wanted - seen:
        sid = (wanted - seen).pop()
        seen.add(sid)
        block = blocks.get(sid, "")
        used.append(block)
        wanted |= set(re.findall(r'<w:(?:basedOn|link) w:val="([^"]+)"', block))
    fonts = re.findall(
        r'w:(?:ascii|hAnsi|cs|eastAsia)="([^"]+)"',
        " ".join(re.findall(r"<w:rFonts [^>]*>", " ".join([body, *used]))),
    )
    return {name.lower() for name in fonts} - installed


def _kill_automation_word() -> None:
    """Word started for automation only; a Word the user opened is left alone."""
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='WINWORD.EXE'\" | "
            "Where-Object { $_.CommandLine -like '*/Automation*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }",
        ],
        check=False,
        capture_output=True,
    )


def _run(command: list[str], env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=_TIMEOUT_S, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        raise PreviewError(f"Preview conversion failed: {error}") from error


def detect_previewer() -> Previewer | None:
    """LibreOffice if installed, otherwise Word on Windows, otherwise no preview."""
    for name in ("soffice", "libreoffice"):
        executable = shutil.which(name)
        if executable:
            return LibreOfficePreviewer(executable)
    default_soffice = Path("C:/Program Files/LibreOffice/program/soffice.exe")
    if default_soffice.is_file():
        return LibreOfficePreviewer(str(default_soffice))
    if sys.platform == "win32" and _word_installed():
        return WordPreviewer()
    return None


def _word_installed() -> bool:
    try:
        import winreg  # noqa: PLC0415 - Windows-only module

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application"))
    except OSError:
        return False
    return True
