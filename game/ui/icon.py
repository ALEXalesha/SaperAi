"""Иконка программы: мина на клетке и тепловая клетка «Мыслей ИИ» рядом, нарисованные
кодом. Её же собирает в .ico build.py."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.18, size * 0.18)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, size, size), QColor("#1f242e"))
    cell = size / 4
    colors = ["#2dd4a8", "#3fae8f", "#9a6b5a", "#ff5b5b"]
    for y in range(4):
        for x in range(4):
            c = QColor(colors[(x + y) % 4] if (x + y) % 3 else "#2f3540")
            c.setAlpha(200 if (x + y) % 3 else 255)
            p.fillRect(QRectF(x * cell + 2, y * cell + 2, cell - 4, cell - 4), c)
    c = QPointF(size / 2, size / 2)
    rad = size * 0.2
    p.setPen(QPen(QColor("#e6e8ec"), max(1.0, size * 0.035)))
    for k in range(4):
        a = k * math.pi / 4
        dx, dy = math.cos(a) * rad * 1.5, math.sin(a) * rad * 1.5
        p.drawLine(QPointF(c.x() - dx, c.y() - dy), QPointF(c.x() + dx, c.y() + dy))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0e1116"))
    p.drawEllipse(c, rad, rad)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(c.x() - rad * 0.35, c.y() - rad * 0.35), rad * 0.22, rad * 0.22)
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(s)))
    return icon
