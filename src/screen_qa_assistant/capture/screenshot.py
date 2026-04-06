from __future__ import annotations

from pathlib import Path

import mss
import mss.tools
from PySide6.QtCore import QRect


class ScreenshotService:
    def grab_region(self, rect: QRect) -> bytes:
        region = {
            "left": rect.x(),
            "top": rect.y(),
            "width": rect.width(),
            "height": rect.height(),
        }
        with mss.mss() as capturer:
            shot = capturer.grab(region)
            return mss.tools.to_png(shot.rgb, shot.size)

    def save_png(self, png_bytes: bytes, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes)
        return path
