"""Стартовое меню Сапёра - «полевая карта».

Свой стиль (правило автора 17.10: у каждой игры своё меню): на весь фон - минное поле, которое
разминирует ИИ: волна открывает клетки от точки старта, цифры как в классическом сапёре, на мины
встают флажки, перед волной - тепловая полоса «Мыслей ИИ». Слева - квадратная панель-планшет
без скруглений: заголовок рубленым Bahnschrift с разрядкой, кнопки - выпуклые клетки поля с
цифрой слева, переключатели моноширинным Consolas. Всё масштабируется от размера окна (до 4K).

Общее из aikit.menu - только живой фон (Backdrop: тикает, пока меню видно), заголовок Title и
законы раскладки.
"""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout

from aikit.menu import Backdrop, Title
from aikit.widgets import fit_segments, label, segmented
from game.ai.agents import LEVELS as AI_LEVELS

MENU_PRESETS = ("beginner", "intermediate", "expert", "custom")

PALETTES = {
    "dark": {
        "bg": "#121611", "closed": "#2c3427", "hi": "#3d4835", "lo": "#191e16", "open": "#1b2019",
        "line": "#0f120d", "text": "#e9ecdf", "muted": "#a3a98f", "accent": "#d9c26a",
        "accent_text": "#1a1c10", "panel": "rgba(15, 19, 13, 222)", "panel_line": "#56603f",
        "flag": "#ff5b4a", "safe": "#47c27a", "risk": "#ff5b4a", "wave": "#d9c26a",
        "digits": ("#6aa7ff", "#58c46a", "#ff6b5b", "#b48cff", "#ffa24a", "#3fd0c9", "#e6e6e6", "#9aa0a6"),
    },
    "light": {
        "bg": "#d9dccb", "closed": "#c4c9b0", "hi": "#e6e9d8", "lo": "#959b80", "open": "#eceee2",
        "line": "#aeb398", "text": "#1d2216", "muted": "#555b45", "accent": "#6f5f12",
        "accent_text": "#fbf8e8", "panel": "rgba(247, 248, 239, 232)", "panel_line": "#8e9471",
        "flag": "#d0342c", "safe": "#1f8a35", "risk": "#d0342c", "wave": "#8a7414",
        "digits": ("#1f5fd1", "#1f8a35", "#d0342c", "#5b2aa8", "#a0521a", "#14857f", "#333333", "#666666"),
    },
}

PERIOD = 16.0          # секунд на одно поле: волна, пауза, затухание
WAVE = 0.34            # секунд на клетку расстояния
DENSITY = 0.17


def palette(name):
    return PALETTES.get(name, PALETTES["dark"])


def menu_board(cols, rows, cycle):
    """Поле фона: мины, числа и время открытия каждой клетки (волна от точки старта).
    Детерминировано по (cols, rows, cycle) - кадр README и законы видят одно и то же."""
    rng = random.Random(cycle * 7919 + cols * 31 + rows)
    sx = rng.randint(int(cols * 0.5), max(int(cols * 0.5), int(cols * 0.8)))
    sy = rng.randint(int(rows * 0.3), max(int(rows * 0.3), int(rows * 0.7)))
    n = cols * rows
    mine = [False] * n
    for i in range(n):
        x, y = i % cols, i // cols
        if abs(x - sx) <= 1 and abs(y - sy) <= 1:
            continue                       # первый клик открывает область
        mine[i] = rng.random() < DENSITY
    num = [0] * n
    for i in range(n):
        x, y = i % cols, i // cols
        num[i] = sum(mine[(y + dy) * cols + x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                     if (dx or dy) and 0 <= x + dx < cols and 0 <= y + dy < rows)
    when = [0.0] * n
    far = max(math.hypot(x - sx, y - sy) for x in (0, cols - 1) for y in (0, rows - 1))
    wave = min(WAVE, 10.0 / max(1.0, far))       # всё поле открыто до затухания при любой ширине
    for i in range(n):
        x, y = i % cols, i // cols
        d = math.hypot(x - sx, y - sy)
        when[i] = 0.6 + d * wave + rng.random() * 0.5 + (0.45 if mine[i] else 0.0)
    order = sorted(range(n), key=lambda i: when[i])
    return {"cols": cols, "rows": rows, "mine": mine, "num": num, "when": when, "order": order,
            "start": (sx, sy), "wave": wave, "risk": [rng.uniform(0.55, 0.95) if mine[i] else rng.uniform(0.03, 0.4)
                                       for i in range(n)]}


def field_tiles(c, theme_name):
    """Клетки поля c×c: закрытая с фаской, открытые 0-8 с цифрой, флажок. Общие для живого фона
    меню и неподвижного фона страниц настроек и статистики (game/ui/skin.py)."""
    pal = palette(theme_name)
    tiles = {}
    closed = QPixmap(c, c)
    closed.fill(QColor(pal["closed"]))
    p = QPainter(closed)
    b = max(2, c // 12)
    p.fillRect(0, 0, c, b, QColor(pal["hi"]))
    p.fillRect(0, 0, b, c, QColor(pal["hi"]))
    p.fillRect(0, c - b, c, b, QColor(pal["lo"]))
    p.fillRect(c - b, 0, b, c, QColor(pal["lo"]))
    p.end()
    tiles["closed"] = closed
    font = QFont("Consolas")
    font.setPixelSize(round(c * 0.58))
    font.setWeight(QFont.Weight.Bold)
    for k in range(0, 9):
        t = QPixmap(c, c)
        t.fill(QColor(pal["open"]))
        p = QPainter(t)
        p.setPen(QColor(pal["line"]))
        p.drawRect(0, 0, c - 1, c - 1)
        if k:
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            p.setFont(font)
            p.setPen(QColor(pal["digits"][k - 1]))
            p.drawText(QRectF(0, 0, c, c), int(Qt.AlignmentFlag.AlignCenter), str(k))
        p.end()
        tiles[k] = t
    flag = QPixmap(closed)
    p = QPainter(flag)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(pal["text"]), max(1.5, c * 0.06)))
    p.drawLine(QPointF(c * 0.42, c * 0.22), QPointF(c * 0.42, c * 0.78))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(pal["flag"]))
    p.drawPolygon([QPointF(c * 0.44, c * 0.22), QPointF(c * 0.78, c * 0.36), QPointF(c * 0.44, c * 0.5)])
    p.setBrush(QColor(pal["text"]))
    p.drawRect(QRectF(c * 0.28, c * 0.74, c * 0.3, c * 0.07))
    p.end()
    tiles["flag"] = flag
    return tiles


class MineField(Backdrop):
    """Фон: ИИ разминирует поле волной. Открытые клетки копятся в картинке (рисуются один раз),
    каждый кадр - только картинка, тепловая полоса перед волной и кольцо волны."""

    FPS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._key = None
        self._acc = None
        self._acc_i = 0
        self._board = None
        self._tiles = {}

    def cell_size(self, h=None):
        return max(26, round((h or self.height()) / 19))

    def _prepare(self, w, h, cycle):
        c = self.cell_size(h)
        cols, rows = w // c + 2, h // c + 2
        key = (cols, rows, cycle, c, self.theme_name, w, h)
        if key != self._key:
            self._key = key
            self._board = menu_board(cols, rows, cycle)
            self._tiles = self._make_tiles(c)
            self._acc = QPixmap(w, h)
            self._acc.fill(QColor(palette(self.theme_name)["bg"]))
            p = QPainter(self._acc)
            for i in range(cols * rows):
                p.drawPixmap(self._cell_pos(i, c), self._tiles["closed"])
            p.end()
            self._acc_i = 0
        return c

    def _cell_pos(self, i, c):
        b = self._board
        return QPointF((i % b["cols"]) * c - c // 3, (i // b["cols"]) * c - c // 4).toPoint()

    def _make_tiles(self, c):
        return field_tiles(c, self.theme_name)

    def paint_scene(self, p, w, h, t):
        cycle, local = divmod(t, PERIOD)
        c = self._prepare(w, h, int(cycle))
        b = self._board
        if local < self._last_local():
            self._key = None                         # время пошло назад (set_time) - собрать заново
            c = self._prepare(w, h, int(cycle))
        order, when = b["order"], b["when"]
        acc = QPainter(self._acc)
        while self._acc_i < len(order) and when[order[self._acc_i]] <= local:
            i = order[self._acc_i]
            tile = self._tiles["flag"] if b["mine"][i] else self._tiles[b["num"][i]]
            acc.drawPixmap(self._cell_pos(i, c), tile)
            self._acc_i += 1
        acc.end()
        self._acc_local = local
        p.drawPixmap(0, 0, self._acc)
        pal = palette(self.theme_name)
        calm = QColor(pal["bg"])
        calm.setAlpha(70)                  # фон спокойнее панели
        p.fillRect(0, 0, w, h, calm)
        # тепловая полоса «Мыслей ИИ» перед волной: риск по клетке, пульсирует
        k = self._acc_i
        pulse = 0.5 + 0.5 * math.sin(t * 5.0)
        while k < len(order) and when[order[k]] <= local + 0.9:
            i = order[k]
            r = b["risk"][i]
            col = QColor(pal["risk"] if r > 0.5 else pal["safe"])
            col.setAlpha(round(60 + 70 * pulse * (1.0 - (when[i] - local) / 0.9)))
            pos = self._cell_pos(i, c)
            p.fillRect(QRectF(pos.x() + 2, pos.y() + 2, c - 4, c - 4), col)
            k += 1
        # кольцо волны
        sx, sy = b["start"]
        radius = max(0.0, (local - 0.6) / b["wave"]) * c
        if radius < math.hypot(w, h) * 1.2:
            ring = QColor(pal["wave"])
            ring.setAlpha(70)
            p.setPen(QPen(ring, max(2.0, c * 0.08)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            centre = self._cell_pos(sx + sy * b["cols"], c)
            p.drawEllipse(QPointF(centre.x() + c / 2, centre.y() + c / 2), radius, radius)
        # начало и конец круга - плавно
        fade = 0.0
        if local < 0.6:
            fade = 1.0 - local / 0.6
        elif local > PERIOD - 1.6:
            fade = (local - (PERIOD - 1.6)) / 1.6
        if fade > 0:
            veil = QColor(pal["bg"])
            veil.setAlphaF(min(1.0, fade))
            p.fillRect(0, 0, w, h, veil)

    def _last_local(self):
        return getattr(self, "_acc_local", 0.0)

    def set_theme(self, name):
        self._key = None
        super().set_theme(name)


class TileButton(QPushButton):
    """Кнопка-клетка: выпуклая, с цифрой сапёра слева (цифра своим цветом)."""

    def __init__(self, digit, slot):
        super().__init__("")
        self.digit = digit
        self.digit_color = QColor("#6aa7ff")
        self.digit_px = 22
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("tile")
        self.clicked.connect(lambda _=False: slot())

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = QFont("Consolas")
        f.setPixelSize(self.digit_px)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(self.digit_color)
        box = QRectF(0, 0, self.digit_px * 2.0, self.height())
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(self.digit))
        p.end()


def qss(pal, k):
    """Таблица стилей меню; k - масштаб от размера окна (1 - обычное окно, до ~1.9 на 4K)."""
    def px(v):
        return f"{round(v * k)}px"
    return f"""
QFrame#saperPanel {{
    background: {pal['panel']};
    border: {px(2)} solid {pal['panel_line']};
    border-radius: 0;
}}
QLabel#saperTag {{ font-family: "Consolas"; font-size: {px(13)}; color: {pal['accent']}; }}
QLabel#saperSub {{ font-family: "Segoe UI"; font-size: {px(14)}; color: {pal['muted']}; }}
QLabel#saperCaption {{ font-family: "Consolas"; font-size: {px(13)}; color: {pal['muted']}; }}
QLabel#saperFoot {{ font-family: "Consolas"; font-size: {px(12)}; color: {pal['muted']}; }}
QPushButton#seg {{
    font-family: "Consolas"; font-size: {px(13)};
    border-radius: 0; padding: {px(5)} {px(8)};
    background: {pal['open']}; color: {pal['text']};
    border: 1px solid {pal['panel_line']};
}}
QPushButton#seg:checked {{ background: {pal['accent']}; color: {pal['accent_text']}; border-color: {pal['accent']}; }}
QPushButton#seg:disabled {{ color: {pal['panel_line']}; }}
QPushButton#tile, QPushButton#tilePrimary {{
    font-family: "Bahnschrift", "Segoe UI"; font-size: {px(18)}; font-weight: 600;
    text-align: left;
    padding: {px(10)} {px(16)} {px(10)} {px(52)};
    border-style: solid; border-width: {px(3)}; border-radius: 0;
    border-color: {pal['hi']} {pal['lo']} {pal['lo']} {pal['hi']};
    background: {pal['closed']}; color: {pal['text']};
}}
QPushButton#tilePrimary {{ background: {pal['accent']}; color: {pal['accent_text']}; }}
QPushButton#tile:hover {{ background: {pal['hi']}; }}
QPushButton#tile:pressed, QPushButton#tilePrimary:pressed {{
    border-color: {pal['lo']} {pal['hi']} {pal['hi']} {pal['lo']};
}}
"""


def page_qss(pal):
    """Фон страницы поля - тот же, что под меню."""
    return f"QWidget#page {{ background: {pal['bg']}; }}"


def side_qss(pal):
    """Боковая панель поля в стиле меню: квадратный планшет, кнопки-клетки с фаской,
    подписи моноширинным Consolas, заголовок рубленым Bahnschrift цвета латуни."""
    return f"""
QFrame#card {{
    background: {pal['panel']};
    border: 2px solid {pal['panel_line']};
    border-radius: 0;
}}
QLabel {{ color: {pal['text']}; }}
QLabel#section {{ font-family: "Bahnschrift", "Segoe UI"; font-size: 20px; font-weight: 700; color: {pal['accent']}; }}
QLabel#muted {{ font-family: "Consolas"; font-size: 13px; color: {pal['muted']}; }}
QLabel#hint {{ font-family: "Consolas"; font-size: 12px; color: {pal['muted']}; }}
QLabel#bigNumber {{ font-family: "Consolas"; font-size: 28px; font-weight: 700; color: {pal['text']}; }}
QLabel#status {{ font-family: "Bahnschrift", "Segoe UI"; font-size: 19px; font-weight: 700; color: {pal['text']}; }}
QLabel#statusWin {{ font-family: "Bahnschrift", "Segoe UI"; font-size: 19px; font-weight: 700; color: {pal['safe']}; }}
QLabel#statusLoss {{ font-family: "Bahnschrift", "Segoe UI"; font-size: 19px; font-weight: 700; color: {pal['risk']}; }}
QPushButton {{
    font-family: "Bahnschrift", "Segoe UI"; font-size: 15px; font-weight: 600;
    padding: 7px 12px;
    border-style: solid; border-width: 3px; border-radius: 0;
    border-color: {pal['hi']} {pal['lo']} {pal['lo']} {pal['hi']};
    background: {pal['closed']}; color: {pal['text']};
}}
QPushButton:hover {{ background: {pal['hi']}; }}
QPushButton:pressed {{ border-color: {pal['lo']} {pal['hi']} {pal['hi']} {pal['lo']}; }}
QPushButton:disabled {{ color: {pal['panel_line']}; }}
QPushButton#primary {{ background: {pal['accent']}; color: {pal['accent_text']}; }}
QPushButton#seg {{
    font-family: "Consolas"; font-size: 13px; font-weight: 400;
    border-width: 1px; border-color: {pal['panel_line']}; padding: 6px 8px;
    background: {pal['open']};
}}
QPushButton#seg:checked {{ background: {pal['accent']}; color: {pal['accent_text']}; border-color: {pal['accent']}; font-weight: 700; }}
QComboBox {{
    font-family: "Consolas"; font-size: 13px;
    background: {pal['open']}; color: {pal['text']};
    border: 1px solid {pal['panel_line']}; border-radius: 0; padding: 6px 30px 6px 10px;
}}
QComboBox::drop-down {{ border: none; background: transparent; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{ background: {pal['open']}; color: {pal['text']}; selection-background-color: {pal['accent']}; selection-color: {pal['accent_text']}; }}
QSpinBox {{ font-family: "Consolas"; background: {pal['open']}; color: {pal['text']}; border: 1px solid {pal['panel_line']}; border-radius: 0; padding: 4px; }}
QSlider::groove:horizontal {{ height: 6px; background: {pal['open']}; border: 1px solid {pal['panel_line']}; }}
QSlider::sub-page:horizontal {{ background: {pal['accent']}; }}
QSlider::handle:horizontal {{ background: {pal['text']}; width: 12px; margin: -6px 0; border-radius: 0; }}
QCheckBox {{ font-family: "Bahnschrift", "Segoe UI"; font-size: 15px; spacing: 10px; color: {pal['text']}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 0; border: 2px solid {pal['panel_line']}; background: {pal['open']}; }}
QCheckBox::indicator:checked {{ background: {pal['accent']}; border-color: {pal['accent']}; image: none; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""


class MenuPage(MineField):
    """Меню: панель-планшет слева, поле с ИИ - на весь фон."""

    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.scale = None
        root = QHBoxLayout(self)
        self.root = root
        root.addStretch(1)
        side = QVBoxLayout()
        side.addStretch(1)
        self.panel = QFrame()
        self.panel.setObjectName("saperPanel")
        side.addWidget(self.panel)
        side.addStretch(1)
        root.addLayout(side)
        root.addStretch(3)
        col = QVBoxLayout(self.panel)
        self.col = col
        self.tag = label("", "saperTag")
        col.addWidget(self.tag)
        self.title = Title("Bahnschrift", 66, spacing=0.10, min_px=30, align=Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.title)
        self.sub = label("", "saperSub", wrap=True)
        col.addWidget(self.sub)
        grid = QGridLayout()
        self.grid = grid
        self.captions = {}
        rows = (("field", segmented({k: "" for k in MENU_PRESETS}, lambda v: gw.change("preset", v), columns=2)),
                ("who", segmented({"human": "", "ai": ""}, lambda v: gw.change("mode", v))),
                ("ai", segmented({lv: "" for lv in AI_LEVELS}, lambda v: gw.change("ai_level", v))))
        self.seg = {}
        for r, (key, (box, buttons)) in enumerate(rows):
            cap = label("", "saperCaption")
            self.captions[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(box, r, 1)
            self.seg[key] = buttons
        col.addLayout(grid)
        self.play_button = TileButton(1, lambda: gw.menu_play())
        self.play_button.setObjectName("tilePrimary")
        self.new_button = TileButton(2, lambda: gw.new_game())
        self.stats_button = TileButton(3, lambda: gw.show_page("stats"))
        self.settings_button = TileButton(4, lambda: gw.show_page("settings"))
        self.buttons = (self.play_button, self.new_button, self.stats_button, self.settings_button)
        for b in self.buttons:
            col.addWidget(b)
        col.addSpacing(6)
        self.foot = label("", "saperFoot", wrap=True)
        col.addWidget(self.foot)
        self.version = label("", "saperFoot")
        col.addWidget(self.version)
        self.apply_scale(force=True)

    # --- масштаб и тема ---

    def scale_for(self, w, h):
        return round(max(1.0, min(2.4, w / 1280, h / 800)), 2)

    def apply_scale(self, force=False):
        k = self.scale_for(max(self.width(), 900), max(self.height(), 640))
        if not force and k == self.scale:
            return
        self.scale = k
        pal = palette(self.theme_name)
        self.setStyleSheet(qss(pal, k))
        self.title.px = round(66 * k)
        self.title.min_px = round(30 * k)
        self.title.set_color(pal["accent"])
        self.title.updateGeometry()
        m = round(30 * k)
        self.root.setContentsMargins(round(40 * k), round(28 * k), round(40 * k), round(28 * k))
        self.panel.setFixedWidth(round(min(470 * k, max(440, self.width() * 0.46))))
        self.col.setContentsMargins(m, round(26 * k), m, round(22 * k))
        self.col.setSpacing(round(9 * k))
        self.grid.setHorizontalSpacing(round(12 * k))
        self.grid.setVerticalSpacing(round(8 * k))
        for b in self.buttons:
            b.digit_px = round(22 * k)
        self.renumber()
        f = QFont("Consolas")
        f.setPixelSize(round(13 * k))
        f.setWeight(QFont.Weight.Bold)
        fm = QFontMetrics(f)
        for buttons in self.seg.values():
            fit_segments(buttons)
            for btn in buttons.values():     # шрифт меню - Consolas своего кегля, не 14px темы
                need = fm.horizontalAdvance(btn.text()) + 2 * round(8 * k) + 8
                btn.setMinimumWidth(max(btn.minimumWidth(), need))

    def set_theme(self, name):
        super().set_theme(name)
        self.apply_scale(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_scale()
        self.panel.setFixedWidth(round(min(470 * self.scale, max(440, self.width() * 0.46))))

    # --- данные ---

    def sync(self, s, in_progress):
        self.seg["field"][s["preset"]].setChecked(True)
        self.seg["who"][s["mode"]].setChecked(True)
        self.seg["ai"][s["ai_level"]].setChecked(True)
        from game.ai.net import default_net
        self.seg["ai"]["medium"].setEnabled(default_net() is not None)
        t = self.gw.t
        self.play_button.setText(t("menu_continue") if in_progress else t("menu_play"))
        self.new_button.setVisible(in_progress)
        self.renumber()

    def renumber(self):
        """Цифры сапёра у видимых кнопок по порядку: 1, 2, 3... своим цветом, как на поле."""
        pal = palette(self.theme_name)
        n = 0
        for b in self.buttons:
            if b is not self.new_button or not self.new_button.isHidden():
                n += 1
                b.digit = n
                b.digit_color = QColor(pal["accent_text"] if b is self.play_button else pal["digits"][n - 1])
                b.update()

    def retranslate(self, in_progress):
        t = self.gw.t
        self.title.setText(t("menu_title"))
        self.sub.setText(t("menu_sub"))
        for key, cap in self.captions.items():
            cap.setText(t("menu_" + key))
        for k, b in self.seg["field"].items():
            b.setText(t(k))
        self.seg["who"]["human"].setText(t("mode_human"))
        self.seg["who"]["ai"].setText(t("mode_ai"))
        for k, b in self.seg["ai"].items():
            b.setText(t("ai_" + k))
        self.new_button.setText(t("new_game"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.apply_scale(force=True)
        self.sync(self.gw.settings, in_progress)

    def set_info(self, tag, foot, version):
        self.tag.setText(tag)
        self.foot.setText(foot)
        self.version.setText(version)
