"""SaperAi: сапёр с ИИ, который считает точную вероятность мины в каждой клетке.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, ИИ и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "saper",
    "title": {"ru": "Сапёр", "en": "Minesweeper"},
    "summary": {"ru": "Сапёр с ИИ: точные вероятности мин, подсказка и «ИИ играет сам»",
                "en": "Minesweeper with an AI: exact mine odds, hints and an AI that plays by itself"},
    "preview": "docs/preview.png",
    "version": VERSION,
}

APP_NAME = "SaperAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет поля появится на шаге «окно» (docs/plan в spec.md, п. 5)."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
