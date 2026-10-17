"""Поле сапёра своим кодом (QPainter): клетки, цифры, флажки, мины, тепловая карта
«Мыслей ИИ» и рамка подсказки.

Мышь: левая - открыть, правая - флажок, средняя или обе сразу - аккорд (срабатывает,
когда отпущена последняя из двух). Виджет только сообщает о намерении сигналами - правила
решает GameWidget.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from aikit import theme
from game.core.board import BOOM, FLAG, HIDDEN, MINE, WRONG_FLAG

# цвета цифр 1..8: классика сапёра, подобранная под тёмную и светлую тему
NUMBER_COLORS = {
    "dark": ["#6ea8ff", "#55d18a", "#ff6b6b", "#b48cff", "#ff9f43", "#3fd0d4", "#e6e8ec", "#9a9fa8"],
    "light": ["#1f5fd1", "#1a8a4a", "#d8303f", "#3a2a9c", "#9c3a10", "#0f8a8e", "#1b2030", "#5f6575"],
}


def mine_color(p, theme_name):
    """Цвет клетки по вероятности мины: 0 - зелёный, 1 - красный (шкала heat aikit).
    Шкала по корню: 21 % риска - уже не «почти безопасно», а около середины; зелёными
    остаются только клетки, где мины почти наверняка нет."""
    return QColor(*theme.heat(1.0 - 2.0 * math.sqrt(max(0.0, min(1.0, p))), theme_name))


class BoardView(QWidget):
    revealAt = Signal(int)
    flagAt = Signal(int)
    chordAt = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.width_, self.height_ = 9, 9
        self.cells = [HIDDEN] * 81
        self.probs = None          # вероятности «Мыслей ИИ» или None
        self.hint = -1             # клетка подсказки
        self.last = -1             # последняя клетка, открытая ИИ
        self.theme_name = "dark"
        self.field = None          # цвета клеток из меню (game.ui.menu.PALETTES) или None
        self.pressed = -1
        self.buttons = Qt.MouseButton.NoButton
        self.chording = False
        self.enabled_input = True
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 200)

    def set_theme(self, name, field=None):
        self.theme_name = name
        self.field = field
        self.update()

    def set_board(self, width, height, cells, probs=None, hint=-1, last=-1):
        self.width_, self.height_ = width, height
        self.cells = list(cells)
        self.probs = probs
        self.hint = hint
        self.last = last
        self.update()

    # --- геометрия ---

    def cell_size(self):
        return max(8.0, min((self.width() - 4) / self.width_, (self.height() - 4) / self.height_))

    def origin(self):
        s = self.cell_size()
        return (self.width() - s * self.width_) / 2, (self.height() - s * self.height_) / 2

    def cell_rect(self, i):
        s = self.cell_size()
        ox, oy = self.origin()
        x, y = i % self.width_, i // self.width_
        return QRectF(ox + x * s, oy + y * s, s, s)

    def cell_at(self, pos):
        s = self.cell_size()
        ox, oy = self.origin()
        x = int((pos.x() - ox) // s)
        y = int((pos.y() - oy) // s)
        if 0 <= x < self.width_ and 0 <= y < self.height_:
            return y * self.width_ + x
        return -1

    # --- мышь ---

    def mousePressEvent(self, e):
        if not self.enabled_input:
            return
        self.buttons = e.buttons()
        both = (self.buttons & Qt.MouseButton.LeftButton) and (self.buttons & Qt.MouseButton.RightButton)
        if both or e.button() == Qt.MouseButton.MiddleButton:
            self.chording = True
        elif e.button() == Qt.MouseButton.RightButton:
            i = self.cell_at(e.position())
            if i >= 0:
                self.flagAt.emit(i)
        self.pressed = self.cell_at(e.position())
        self.update()

    def mouseReleaseEvent(self, e):
        if not self.enabled_input:
            return
        i = self.cell_at(e.position())
        if self.chording:
            if e.buttons() == Qt.MouseButton.NoButton or e.button() == Qt.MouseButton.MiddleButton:
                self.chording = False
                if i >= 0:
                    self.chordAt.emit(i)
        elif e.button() == Qt.MouseButton.LeftButton and i >= 0:
            self.revealAt.emit(i)
        if e.buttons() == Qt.MouseButton.NoButton:
            self.chording = False
            self.pressed = -1
        self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() != Qt.MouseButton.NoButton:
            i = self.cell_at(e.position())
            if i != self.pressed:
                self.pressed = i
                self.update()

    def contextMenuEvent(self, e):
        e.accept()

    # --- рисование ---

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = theme.palette(self.theme_name)
        s = self.cell_size()
        ox, oy = self.origin()
        f = self.field
        p.fillRect(QRectF(ox - 2, oy - 2, s * self.width_ + 4, s * self.height_ + 4),
                   QColor(f["line"] if f else pal["border"]))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(7, int(s * 0.58)))
        small = QFont("Segoe UI")
        small.setPixelSize(max(6, int(s * 0.34)))
        small.setBold(True)
        nums = NUMBER_COLORS.get(self.theme_name, NUMBER_COLORS["dark"])
        # закрытая клетка заметно отличается от открытой в обеих темах
        hidden_c = QColor(pal["surface2"]) if self.theme_name == "dark" else QColor("#c3cddd")
        hidden_hi = QColor(pal["sq_dark"]) if self.theme_name == "dark" else QColor("#e9eef6")
        hidden_lo = None
        open_c = QColor(pal["surface"])
        if f:                      # поле в цветах «полевой карты» меню: выпуклые клетки с фаской
            nums = list(f["digits"])
            hidden_c, hidden_hi, hidden_lo = QColor(f["closed"]), QColor(f["hi"]), QColor(f["lo"])
            open_c = QColor(f["open"])
        neighbours = self._press_area()
        for i, v in enumerate(self.cells):
            r = self.cell_rect(i).adjusted(0.5, 0.5, -0.5, -0.5)
            if v >= 0 or v in (MINE, BOOM):
                p.fillRect(r, QColor(pal["bad"]) if v == BOOM else open_c)
                if v > 0:
                    p.setFont(font)
                    p.setPen(QColor(nums[v - 1]))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(v))
                elif v in (MINE, BOOM):
                    self._mine(p, r, pal)
                continue
            pressed = i in neighbours and v == HIDDEN
            p.fillRect(r, open_c if pressed else hidden_c)
            if not pressed:
                p.setPen(QPen(hidden_hi, max(1.0, s * 0.06)))
                p.drawLine(r.topLeft() + QPointF(1, 1), r.topRight() + QPointF(-1, 1))
                p.drawLine(r.topLeft() + QPointF(1, 1), r.bottomLeft() + QPointF(1, -1))
                if hidden_lo is not None:
                    p.setPen(QPen(hidden_lo, max(1.0, s * 0.06)))
                    p.drawLine(r.bottomLeft() + QPointF(1, -1), r.bottomRight() + QPointF(-1, -1))
                    p.drawLine(r.topRight() + QPointF(-1, 1), r.bottomRight() + QPointF(-1, -1))
            if self.probs is not None and self.probs[i] is not None and v in (HIDDEN, FLAG):
                c = mine_color(self.probs[i], self.theme_name)
                c.setAlpha(205)
                p.fillRect(r.adjusted(1, 1, -1, -1), c)
                if v == HIDDEN and s >= 20:
                    pct = self.probs[i] * 100
                    text = "0" if pct < 0.05 else "100" if pct > 99.95 else (f"{pct:.0f}" if pct >= 1 else "<1")
                    p.setFont(small)
                    p.setPen(QColor(pal["text"]))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            if v in (FLAG, WRONG_FLAG):
                self._flag(p, r, pal)
                if v == WRONG_FLAG:
                    p.setPen(QPen(QColor(pal["bad"]), max(1.5, s * 0.08)))
                    p.drawLine(r.topLeft() + QPointF(s * 0.2, s * 0.2), r.bottomRight() - QPointF(s * 0.2, s * 0.2))
                    p.drawLine(r.topRight() + QPointF(-s * 0.2, s * 0.2), r.bottomLeft() + QPointF(s * 0.2, -s * 0.2))
        for i, color in ((self.last, pal["select"]), (self.hint, pal["last_move"])):
            if 0 <= i < len(self.cells):
                p.setPen(QPen(QColor(color), max(2.0, s * 0.1)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(self.cell_rect(i).adjusted(1.5, 1.5, -1.5, -1.5))
        p.end()

    def _press_area(self):
        if self.pressed < 0:
            return set()
        if not self.chording:
            return {self.pressed}
        w = self.width_
        x, y = self.pressed % w, self.pressed // w
        return {ny * w + nx for ny in range(y - 1, y + 2) for nx in range(x - 1, x + 2)
                if 0 <= nx < w and 0 <= ny < self.height_}

    def _mine(self, p, r, pal):
        c = r.center()
        rad = r.width() * 0.24
        p.setPen(QPen(QColor(pal["text"] if self.theme_name == "dark" else "#1b2030"), max(1.0, r.width() * 0.07)))
        for k in range(4):
            a = k * math.pi / 4
            dx, dy = math.cos(a) * rad * 1.45, math.sin(a) * rad * 1.45
            p.drawLine(QPointF(c.x() - dx, c.y() - dy), QPointF(c.x() + dx, c.y() + dy))
        p.setBrush(QColor("#1b2030" if self.theme_name == "light" else "#0e1116"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c, rad, rad)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(c.x() - rad * 0.35, c.y() - rad * 0.35), rad * 0.22, rad * 0.22)

    def _flag(self, p, r, pal):
        w = r.width()
        x0, y0 = r.x(), r.y()
        p.setPen(QPen(QColor(pal["text"]), max(1.0, w * 0.07)))
        p.drawLine(QPointF(x0 + w * 0.42, y0 + w * 0.2), QPointF(x0 + w * 0.42, y0 + w * 0.78))
        p.drawLine(QPointF(x0 + w * 0.28, y0 + w * 0.78), QPointF(x0 + w * 0.66, y0 + w * 0.78))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pal["bad"]))
        p.drawPolygon(QPolygonF([QPointF(x0 + w * 0.44, y0 + w * 0.2), QPointF(x0 + w * 0.76, y0 + w * 0.36),
                                 QPointF(x0 + w * 0.44, y0 + w * 0.52)]))
