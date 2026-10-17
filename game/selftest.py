"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Окно
создаётся offscreen, данные игрока - во временной папке. Проверяется: правила (случайные
партии с инвариантами), решатель на позиции против перебора, окно - ИИ сам проходит поле
новичка, человек открывает клетки через окно.
"""
import os
import random
import tempfile
import time
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        home = tempfile.mkdtemp(prefix="saperai-selftest-")
        os.environ["SAPERAI_HOME"] = home
        from PySide6.QtWidgets import QApplication

        import aikit
        from aikit.host import make_window
        from game import APP_NAME, GAME_INFO, create_widget
        from game.ai import solver
        from game.ai.net import default_net
        from game.core.board import Game
        from game.version import VERSION

        lines.append(f"SaperAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        started = time.time()
        rng = random.Random(1)
        for i in range(200):
            g = Game(rng.randint(5, 16), rng.randint(5, 16), rng.randint(3, 20), seed=i)
            for _ in range(60):
                if g.over:
                    break
                k = rng.randrange(g.n)
                (g.reveal if rng.random() < 0.7 else g.toggle_flag)(k)
                if g.mine is not None and g.opened != sum(g.open):
                    raise RuntimeError("счётчик открытых клеток разошёлся")
        lines.append(f"правила: 200 случайных партий без нарушений, {time.time() - started:.2f} с")
        g = Game(9, 9, 10, seed=3)
        g.reveal(40)
        a = solver.analyze(g.observe())
        total = sum(p for p in a.probs if p is not None)
        if abs(total - 10) > 1e-9:
            raise RuntimeError(f"сумма вероятностей {total}, а мин 10")
        lines.append(f"решатель: сумма вероятностей = 10, точно: {'да' if a.exact else 'нет'}")
        lines.append("сеть: " + ("загружена" if default_net() is not None else "нет (средний уровень выключен)"))

        app = QApplication.instance() or QApplication([])
        window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
        window.show()
        gw = window.game
        app.processEvents()
        from aikit.menu import layout_problems
        if gw.current_page() != "menu":
            raise RuntimeError("окно открылось не меню")
        bad = layout_problems(gw.menu)
        if bad:
            raise RuntimeError("меню обрезано: " + "; ".join(bad[:3]))
        lines.append("меню: открыто первым, раскладка цела")
        gw.change("speed_ms", 0)
        gw.change("mode", "ai")
        gw.change("ai_level", "strong")
        t0 = time.time()
        wins = 0
        for seed in range(3):
            gw.new_game(seed=seed)
            end = time.time() + 60
            while not gw.game.over and time.time() < end:
                app.processEvents()
                time.sleep(0.002)
            if not gw.game.over:
                raise RuntimeError("ИИ не доиграл поле новичка за 60 с")
            wins += gw.game.status == "won"
        lines.append(f"окно: ИИ сыграл 3 партии новичка, побед {wins}, {time.time() - t0:.2f} с")
        gw.change("mode", "human")
        gw.new_game(seed=5)
        gw.on_reveal(40)
        if gw.game.opened == 0:
            raise RuntimeError("клик человека не открыл клетку")
        image = window.grab().toImage()
        if image.isNull() or image.width() < 300:
            raise RuntimeError("окно не нарисовалось")
        lines.append(f"окно: клик открыл {gw.game.opened} клеток, кадр {image.width()}x{image.height()}")
        t0 = time.time()
        window.close()
        app.processEvents()
        lines.append(f"окно закрыто за {time.time() - t0:.2f} с")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
