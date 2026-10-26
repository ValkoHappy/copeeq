"""Phone photo -> flat page: find the sheet, undo the perspective.

Everything after reading measures the page (sizes, spacing, cut-outs), so the page must be flat
and upright. A sheet photographed at an angle is a quadrilateral brighter than the table under
it; mapping its corners to a rectangle gives a scan-like page. A photo that is already a scan
(no sheet edges to find) is left as it is. Curved pages need a learned unwarping model (UVDoc,
DocTr); this handles the common case of a flat sheet.
"""

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from foto2word.domain.images import PageImage

_WORK_SIDE = 1000
"""Long side of the copy the sheet is looked for on."""
_MIN_SHEET_SHARE = 0.25
"""A sheet takes at least this share of the photo."""
_A4 = 297 / 210
_A4_TOLERANCE = 0.15
"""A sheet seen at an angle looks longer or shorter than it is (by 12 % in a common phone shot);
Russian documents are A4 nearly always, so anything this close is taken as A4."""
_JPEG_QUALITY = 92

Quad = NDArray[np.float32]


class OpenCvPageRectifier:
    def rectify(self, page: PageImage) -> PageImage:
        decoded = cv2.imdecode(np.frombuffer(page.data, np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            return page
        photo = cast("NDArray[np.uint8]", decoded)
        corners = self._sheet(photo)
        if corners is None:
            return page
        flat = self._unwarp(photo, corners)
        ok, encoded = cv2.imencode(".jpg", flat, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        if not ok:
            return page
        return PageImage(encoded.tobytes(), "image/jpeg", page.source_name)

    def _sheet(self, photo: NDArray[np.uint8]) -> Quad | None:
        """Corners of the largest convex quadrilateral that looks like the sheet."""
        height, width = photo.shape[:2]
        scale = _WORK_SIDE / max(height, width)
        small = cv2.resize(photo, (round(width * scale), round(height * scale)))
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
        area = small.shape[0] * small.shape[1]
        best: Quad | None = None
        best_area = area * _MIN_SHEET_SHARE
        for mask in (bright, edges):
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                hull = cv2.convexHull(contour)
                approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
                size = cv2.contourArea(approx)
                if len(approx) == 4 and size > best_area and size < area * 0.995:  # noqa: PLR2004
                    best, best_area = approx.reshape(4, 2).astype(np.float32), size
        return None if best is None else best / scale

    @staticmethod
    def _unwarp(photo: NDArray[np.uint8], corners: Quad) -> NDArray[np.uint8]:
        top_left, top_right, bottom_right, bottom_left = _ordered(corners)
        width = max(
            np.linalg.norm(top_right - top_left), np.linalg.norm(bottom_right - bottom_left)
        )
        height = max(
            np.linalg.norm(bottom_left - top_left), np.linalg.norm(bottom_right - top_right)
        )
        ratio = height / width
        if abs(ratio - _A4) / _A4 < _A4_TOLERANCE:  # a sheet of A4 seen at an angle: make it A4
            height = width * _A4
        elif abs(1 / ratio - _A4) / _A4 < _A4_TOLERANCE:
            width = height * _A4
        target = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32
        )
        source = np.array([top_left, top_right, bottom_right, bottom_left], np.float32)
        matrix = cv2.getPerspectiveTransform(source, target)
        size = (round(float(width)), round(float(height)))
        flat = cv2.warpPerspective(
            photo, matrix, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return cast("NDArray[np.uint8]", flat)


def _ordered(corners: Quad) -> Quad:
    """Top-left, top-right, bottom-right, bottom-left."""
    total = corners.sum(axis=1)
    difference = np.diff(corners, axis=1).ravel()
    return np.array(
        [
            corners[np.argmin(total)],
            corners[np.argmin(difference)],
            corners[np.argmax(total)],
            corners[np.argmax(difference)],
        ],
        np.float32,
    )
