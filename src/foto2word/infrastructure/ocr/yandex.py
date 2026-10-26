"""Yandex Vision OCR as an independent second reader for verification.

Request format follows the public Vision OCR v1 `recognizeText` API. Not yet exercised against
the live service in this repository: check the first real run.
"""

import base64
from collections.abc import Sequence
from typing import Any, cast

import httpx

from foto2word.domain.document import BoundingBox
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine

ENDPOINT = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
_MIME = {"image/jpeg": "JPEG", "image/png": "PNG", "application/pdf": "PDF"}


class SecondReaderError(Foto2WordError):
    pass


class YandexVisionReader:
    def __init__(
        self, api_key: str, folder_id: str, client: httpx.Client | None = None, model: str = "page"
    ) -> None:
        self._headers = {
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
            "x-data-logging-enabled": "false",
        }
        self._client = client or httpx.Client(timeout=60)
        self._model = model

    def read_text(self, pages: Sequence[PageImage]) -> str:
        return "\n".join(self._recognize(page)["fullText"] for page in pages)

    def read_lines(self, pages: Sequence[PageImage]) -> list[TextLine]:
        """Every text line with its box, normalised to the page size."""
        found: list[TextLine] = []
        for number, page in enumerate(pages, start=1):
            annotation = self._recognize(page)
            try:
                width, height = float(annotation["width"]), float(annotation["height"])
                for block in annotation.get("blocks", []):
                    for line in block.get("lines", []):
                        xs, ys = zip(
                            *(
                                (float(v["x"]), float(v["y"]))
                                for v in line["boundingBox"]["vertices"]
                            ),
                            strict=True,
                        )
                        box = BoundingBox(
                            x0=min(xs) / width, y0=min(ys) / height,
                            x1=max(xs) / width, y1=max(ys) / height,
                        )  # fmt: skip
                        found.append(TextLine(page=number, text=str(line["text"]), box=box))
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
                raise SecondReaderError(f"Unexpected Yandex Vision OCR answer: {error}") from error
        return found

    def _recognize(self, page: PageImage) -> dict[str, Any]:
        payload = {
            "mimeType": _MIME.get(page.media_type, "JPEG"),
            "languageCodes": ["ru", "en"],
            "model": self._model,
            "content": base64.standard_b64encode(page.data).decode("ascii"),
        }
        try:
            response = self._client.post(ENDPOINT, json=payload, headers=self._headers)
            response.raise_for_status()
            annotation = response.json()["result"]["textAnnotation"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise SecondReaderError(f"Yandex Vision OCR failed: {error}") from error
        return cast("dict[str, Any]", annotation)
