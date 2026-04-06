from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


@lru_cache(maxsize=1)
def build_tray_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 128):
        icon.addPixmap(build_tray_icon_pixmap(size))
    return icon


@lru_cache(maxsize=16)
def build_tray_icon_pixmap(size: int) -> QPixmap:
    return _render_icon_pixmap(size)


def _render_icon_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    scale = size / 32.0
    outer = QRectF(2.0 * scale, 2.0 * scale, 28.0 * scale, 28.0 * scale)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FAF8F3"))
    painter.drawRoundedRect(outer, 8.0 * scale, 8.0 * scale)

    border_pen = QPen(QColor("#111111"), max(1.2, 1.8 * scale))
    border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(border_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(outer, 8.0 * scale, 8.0 * scale)

    inner_path = QPainterPath()
    inner_path.moveTo(11.0 * scale, 12.0 * scale)
    inner_path.lineTo(11.0 * scale, 10.0 * scale)
    inner_path.lineTo(21.0 * scale, 10.0 * scale)
    inner_path.lineTo(21.0 * scale, 16.0 * scale)
    inner_path.lineTo(11.0 * scale, 16.0 * scale)
    inner_path.lineTo(11.0 * scale, 22.0 * scale)
    inner_path.lineTo(21.0 * scale, 22.0 * scale)
    painter.drawPath(inner_path)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#111111"))
    painter.drawEllipse(QPointF(22.0 * scale, 22.0 * scale), 2.4 * scale, 2.4 * scale)

    accent_pen = QPen(QColor("#6CCBC2"), max(0.8, 1.4 * scale))
    accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(accent_pen)
    painter.drawLine(QPointF(13.0 * scale, 26.0 * scale), QPointF(20.0 * scale, 26.0 * scale))

    painter.end()
    return pixmap
