import json
from io import BytesIO
from pathlib import Path

import docx
import pytest
from PIL import Image
from typer.testing import CliRunner

from foto2word.cli.main import app
from foto2word.domain.errors import InvalidImageError
from foto2word.infrastructure.images import PillowImageLoader
from tests.conftest import CASES

runner = CliRunner()


def test_loader_converts_to_jpeg_and_limits_size(tmp_path: Path) -> None:
    path = tmp_path / "page.webp"
    Image.new("RGB", (4000, 3000), "white").save(path, format="WEBP")

    page = PillowImageLoader(max_side_px=2048).load(path)

    assert page.media_type == "image/jpeg"
    assert Image.open(BytesIO(page.data)).size == (2048, 1536)


def test_loader_rejects_non_images(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not an image", encoding="utf-8")

    with pytest.raises(InvalidImageError):
        PillowImageLoader().load(path)


def test_cli_render_builds_docx_from_saved_model(tmp_path: Path) -> None:
    output = tmp_path / "act.docx"

    result = runner.invoke(
        app, ["render", str(CASES / "act-hydro-001" / "expected.docmodel.json"), "-o", str(output)]
    )

    assert result.exit_code == 0, result.output
    assert "правка: «2026гг.» -> «2027 г.»" in result.output
    result.output.encode("cp1251")  # must print on a legacy Windows console
    assert docx.Document(str(output)).paragraphs[0].text == "АКТ"


def test_cli_schema_prints_json() -> None:
    result = runner.invoke(app, ["schema"])

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "Document"


def test_cli_convert_without_api_key_fails_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    photo = CASES / "act-hydro-001" / "photo-1.webp"

    result = runner.invoke(app, ["convert", str(photo), "-o", str(tmp_path / "out.docx")])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output
