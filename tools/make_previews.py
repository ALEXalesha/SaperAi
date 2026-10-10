"""Кадры для README: окно без экрана в нескольких состояниях.

    python tools/make_previews.py [папка]     # по умолчанию docs/
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aikit import offscreen  # noqa: E402

offscreen.setup(force=True)
os.environ["SAPERAI_HOME"] = tempfile.mkdtemp(prefix="saperai-previews-")


def pump(app, cond=lambda: False, limit=20.0):
    end = time.time() + limit
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.005)


def play_ai_until(app, gw, opened_share, limit=60.0):
    """ИИ играет, пока не откроет долю поля (или не кончится партия)."""
    g = gw.game
    target = (g.n - g.mines) * opened_share
    pump(app, lambda: gw.game.over or gw.game.opened >= target, limit)


def main(out):
    from PySide6.QtWidgets import QApplication

    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget

    os.makedirs(out, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=os.environ["SAPERAI_HOME"])
    window.resize(1280, 800)
    window.show()
    gw = window.game
    shots = []
    for theme_name in ("dark", "light"):
        ctx.set_theme(theme_name)
        suffix = "" if theme_name == "dark" else "_light"
        # профи: ИИ сыграл часть поля, «Мысли ИИ» поверх
        gw.change("preset", "expert")
        gw.change("ai_level", "strong")
        gw.change("speed_ms", 0)
        gw.change("show_thoughts", False)
        gw.change("mode", "ai")
        for seed in range(40, 80):
            gw.new_game(seed=seed)
            play_ai_until(app, gw, 0.45)
            if not gw.game.over:
                break
        gw.toggle_pause()                     # пауза: поле остаётся, «Мысли ИИ» поверх
        gw.change("show_thoughts", True)
        pump(app, lambda: gw.probs is not None, 20)
        pump(app, limit=0.3)
        shots.append((f"preview_expert{suffix}.png", window.grab()))
        gw.change("show_thoughts", False)
        gw.change("mode", "human")
        # новичок: человек открыл поле, подсказка
        gw.change("preset", "beginner")
        gw.new_game(seed=12)
        gw.on_reveal(40)
        gw.on_hint()
        pump(app, lambda: gw.hint_cell >= 0, 10)
        pump(app, limit=0.3)
        shots.append((f"preview_hint{suffix}.png", window.grab()))
        gw.show_page("stats")
        pump(app, limit=0.3)
        shots.append((f"preview_stats{suffix}.png", window.grab()))
        gw.show_page("play")
    for name, pix in shots:
        pix.save(os.path.join(out, name))
        print(name, pix.width(), pix.height())
    first = shots[0][1]
    first.save(os.path.join(out, "preview.png"))
    gw.shutdown()
    window.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs"))
