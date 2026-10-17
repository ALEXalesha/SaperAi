"""Вид страниц «Настройки» и «Статистика» и боковой панели Сапёра - та же «полевая карта», что
и стартовое меню (правило автора 17.10: настройки и статистика у каждой игры свои).

Фон страниц - неподвижное минное поле: закрытые клетки с фаской, разминированный угол с цифрами
и флажками, притушенный цветом фона. Карточки и кнопки - выпуклые клетки с фаской (bevel),
без скруглений; заголовок - рубленый Bahnschrift заглавными с разрядкой цвета латуни; числа и
подписи таблиц - моноширинный Consolas. Счётчики мин и времени на боковой панели - табло
классического сапёра (тёмное окошко с красными цифрами).

Механизм общий (aikit.skin), здесь - только стиль Сапёра.
"""
import math

from PySide6.QtGui import QColor

from aikit.skin import Skin
from game.ui.menu import field_tiles, menu_board
from game.ui.menu import palette as menu_palette

LCD = {"dark": ("#0b0d09", "#ff4a3a"), "light": ("#1d2216", "#ff5b4a")}


class SaperSkin(Skin):
    key = "saper-field"
    palettes = {
        "dark": {"bg": "#121611", "surface": "#1a1f17", "surface2": "#2c3427", "border": "#56603f",
                 "text": "#e9ecdf", "muted": "#a3a98f", "accent": "#d9c26a", "accent_text": "#1a1c10",
                 "good": "#47c27a", "bad": "#ff5b4a", "warn": "#ffa24a", "grid": "#2c3427",
                 "hi": "#3d4835", "lo": "#0f120d", "button": "#2c3427", "field": "#1b2019"},
        "light": {"bg": "#d9dccb", "surface": "#eceee2", "surface2": "#c4c9b0", "border": "#8e9471",
                  "text": "#1d2216", "muted": "#555b45", "accent": "#6f5f12", "accent_text": "#fbf8e8",
                  "good": "#1f8a35", "bad": "#d0342c", "warn": "#a0521a", "grid": "#c4c9b0",
                  "hi": "#f7f8ef", "lo": "#959b80", "button": "#c4c9b0", "field": "#f7f8ef"},
    }
    heading_family = "Bahnschrift"
    heading_px = 34
    heading_upper = True
    heading_spacing = 0.08
    heading_color = "accent"
    section_family = "Bahnschrift"
    section_color = "accent"
    body_family = "Segoe UI"
    mono_family = "Consolas"
    radius = 0
    control_radius = 0
    card_style = "bevel"
    button_style = "bevel"
    card_alpha = 240

    def extra_qss(self, p, theme):
        return f"""
QLabel#hint, QLabel#muted {{ font-family: "Consolas"; }}
QHeaderView::section {{ font-family: "Consolas"; font-weight: 700; border-bottom: 2px solid {p['border']}; }}
QTableWidget {{ font-family: "Consolas"; }}
QLabel#skinTag {{ font-family: "Consolas"; font-size: 13px; }}
"""

    def paint_backdrop(self, p, w, h, pal, theme):
        """Неподвижное поле: закрытые клетки, разминированный правый нижний угол, флажки на минах."""
        c = max(26, round(h / 19))
        cols, rows = w // c + 2, h // c + 2
        board = menu_board(cols, rows, 3)
        tiles = field_tiles(c, theme)
        sx, sy = cols * 0.95, rows * 1.05
        far = math.hypot(cols, rows) * 0.48
        for i in range(cols * rows):
            x, y = i % cols, i // cols
            opened = math.hypot(x - sx, y - sy) < far + 2.2 * math.sin(x * 0.9 + y * 0.7)
            tile = tiles["closed"]
            if opened:
                tile = tiles["flag"] if board["mine"][i] else tiles[board["num"][i]]
            p.drawPixmap(x * c - c // 3, y * c - c // 4, tile)
        veil = QColor(menu_palette(theme)["bg"])
        veil.setAlphaF(0.62)
        p.fillRect(0, 0, w, h, veil)


SKIN = SaperSkin()


def lcd_qss(theme):
    """Табло мин и времени на боковой панели - как у классического сапёра."""
    back, digits = LCD.get(theme, LCD["dark"])
    pal = menu_palette(theme)
    return f"""
QLabel#fieldStats {{
    font-family: "Consolas"; font-size: 14px; font-weight: 700; color: {pal['accent']};
    background: {pal['open']}; padding: 6px 8px; border-style: solid; border-width: 2px;
    border-color: {pal['lo']} {pal['hi']} {pal['hi']} {pal['lo']};
}}
QLabel#bigNumber {{
    font-family: "Consolas"; font-size: 26px; font-weight: 700; color: {digits};
    background: {back}; padding: 1px 8px; border-style: solid; border-width: 2px;
    border-color: {pal['lo']} {pal['hi']} {pal['hi']} {pal['lo']};
}}
"""

