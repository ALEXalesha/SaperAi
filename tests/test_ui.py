"""Окно без экрана (Qt offscreen): клики мышью собранными событиями, флажки, аккорд,
ИИ играет сам, пауза, подсказка, «Мысли ИИ», рекорды, темы, языки, остановка за 2 секунды.
Ожидания - с тайм-аутом; настоящий курсор не трогается."""
import time

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from game import APP_NAME, GAME_INFO, create_widget
from game.core.board import FLAG, HIDDEN, Observation
from game.ui.i18n import EN, RU


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    w.game.show_page("play")          # окно открывается меню (tests/test_menu.py), здесь - поле
    w.game.change("speed_ms", 0)
    yield w
    w.game.shutdown()
    w.close()


def wait(app, cond, limit=30.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.002)
    return cond()


def mouse(view, kind, button, buttons, pos):
    ev = QMouseEvent(kind, QPointF(pos), QPointF(view.mapToGlobal(pos.toPoint())), button, buttons,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, ev)


def click(view, i, button=Qt.MouseButton.LeftButton):
    pos = view.cell_rect(i).center()
    mouse(view, QMouseEvent.Type.MouseButtonPress, button, button, pos)
    mouse(view, QMouseEvent.Type.MouseButtonRelease, button, Qt.MouseButton.NoButton, pos)


def win_by_hand(gw):
    """Открыть все клетки без мин кликами окна (тест знает раскладку, окно - нет)."""
    g = gw.game
    if g.mine is None:
        gw.on_reveal(g.n // 2)          # первый клик раскладывает мины
    for i in range(g.n):
        if not g.mine[i] and not g.open[i]:
            gw.on_reveal(i)


def test_translations_complete():
    assert set(RU) == set(EN)


def test_mouse_left_opens_right_flags(app, win):
    gw = win.game
    gw.new_game(seed=1)
    view = gw.play.board
    click(view, 40)
    assert gw.game.opened > 0 and gw.game.status == "playing"
    hidden = next(i for i in range(gw.game.n) if not gw.game.open[i])
    click(view, hidden, Qt.MouseButton.RightButton)
    assert gw.game.flag[hidden] and gw.play.mines_value.text() == "9"
    click(view, hidden, Qt.MouseButton.RightButton)
    assert not gw.game.flag[hidden]


def test_chord_by_middle_and_both_buttons(app, win):
    gw = win.game
    for seed in range(50):
        gw.new_game(seed=seed)
        g = gw.game
        gw.on_reveal(40)
        # открытая цифра, у которой есть закрытые соседи, а мины рядом можно пометить
        cand = [i for i in range(g.n) if g.open[i] and g.count[i] > 0
                and any(not g.open[j] and not g.mine[j] for j in g.nb[i])]
        if g.status == "playing" and cand:
            break
    i = cand[0]
    for j in g.nb[i]:
        if g.mine[j]:
            g.toggle_flag(j)
    view = gw.play.board
    pos = view.cell_rect(i).center()
    L, R = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
    mouse(view, QMouseEvent.Type.MouseButtonPress, L, L, pos)
    mouse(view, QMouseEvent.Type.MouseButtonPress, R, L | R, pos)
    before = g.opened
    mouse(view, QMouseEvent.Type.MouseButtonRelease, R, L, pos)
    mouse(view, QMouseEvent.Type.MouseButtonRelease, L, Qt.MouseButton.NoButton, pos)
    assert g.opened > before
    assert all(g.open[j] or g.flag[j] for j in g.nb[i])
    # средняя кнопка - то же самое (на открытой цифре без закрытых соседей - ничего)
    M = Qt.MouseButton.MiddleButton
    mouse(view, QMouseEvent.Type.MouseButtonPress, M, M, pos)
    mouse(view, QMouseEvent.Type.MouseButtonRelease, M, Qt.MouseButton.NoButton, pos)
    assert g.status in ("playing", "won")


def test_human_win_records_stats_and_time(app, win):
    gw = win.game
    gw.new_game(seed=3)
    win_by_hand(gw)
    assert gw.game.status == "won"
    e = gw.ctx.stats.entry("beginner/opening")
    assert e["games"] == 1 and e["wins"] == 1
    assert len(gw.records()["beginner/opening"]) == 1
    assert gw.play.status.text() == RU["status_won"]


def test_hint_makes_game_assisted(app, win):
    gw = win.game
    gw.new_game(seed=4)
    gw.on_reveal(40)
    gw.on_hint()
    assert wait(app, lambda: gw.hint_cell >= 0)
    assert gw.assisted
    win_by_hand(gw)
    assert gw.ctx.stats.entry("beginner/opening")["games"] == 0


def test_hint_safe_cell_is_safe(app, win):
    gw = win.game
    for seed in range(20):
        gw.new_game(seed=seed)
        gw.on_reveal(40)
        gw.on_hint()
        assert wait(app, lambda: gw.hint_cell >= 0)
        if gw.message == RU["hint_safe"]:
            assert not gw.game.mine[gw.hint_cell]


def test_ai_plays_itself_and_is_not_recorded(app, win):
    gw = win.game
    gw.change("mode", "ai")
    gw.new_game(seed=6)
    assert wait(app, lambda: gw.game.over, 60)
    assert gw.ctx.stats.entry("beginner/opening")["games"] == 0
    assert gw.history.games == []                   # и в журнал графиков показ не идёт
    assert gw.play.status.text() in (RU["status_ai_won"], RU["status_ai_lost"])
    gw.change("mode", "human")


def test_ai_flags_sure_mines_correctly(app, win):
    gw = win.game
    gw.change("preset", "intermediate")
    gw.change("mode", "ai")
    gw.new_game(seed=8)
    assert wait(app, lambda: gw.game.over or gw.game.flags >= 5, 60)
    g = gw.game
    assert all(g.mine[i] for i in range(g.n) if g.flag[i])
    gw.change("mode", "human")


def test_pause_stops_ai(app, win):
    gw = win.game
    gw.change("preset", "expert")
    gw.change("speed_ms", 200)
    gw.change("mode", "ai")
    gw.new_game(seed=9)
    assert wait(app, lambda: gw.game.opened > 0, 20)
    gw.toggle_pause()
    wait(app, lambda: not gw.ai.busy(), 5)
    opened = gw.game.opened
    wait(app, lambda: False, 0.8)
    assert gw.game.opened == opened and gw.play.pause_button.text() == RU["resume"]
    gw.toggle_pause()
    assert wait(app, lambda: gw.game.opened > opened or gw.game.over, 20)
    gw.change("mode", "human")


def test_ai_receives_only_observation(app, win):
    gw = win.game
    seen = []
    orig = gw.ai.request_move

    def spy(token, obs, level, seed):
        seen.append(obs)
        return orig(token, obs, level, seed)

    gw.ai.request_move = spy
    gw.change("mode", "ai")
    gw.new_game(seed=10)
    assert wait(app, lambda: gw.game.over, 60)
    assert seen and all(type(o) is Observation for o in seen)
    gw.change("mode", "human")


def test_thoughts_heatmap_and_sources(app, win):
    gw = win.game
    gw.new_game(seed=11)
    gw.on_reveal(40)
    gw.change("show_thoughts", True)
    assert wait(app, lambda: gw.probs is not None)
    view = gw.play.board
    assert view.probs is not None
    hidden = [i for i, v in enumerate(view.cells) if v == HIDDEN]
    assert all(view.probs[i] is not None for i in hidden)
    assert abs(sum(view.probs[i] for i in hidden) - 10) < 1e-6
    assert gw.play.thoughts_source.text() == RU["thoughts_exact"]
    assert gw.assisted
    gw.change("ai_level", "novice")
    assert wait(app, lambda: gw.thoughts_info and gw.thoughts_info["source"] == "novice")
    assert all(p in (None, 0.0, 1.0) for p in gw.probs)
    gw.change("ai_level", "strong")
    gw.change("show_thoughts", False)
    assert gw.play.board.probs is None


def test_flagged_cells_still_get_probabilities(app, win):
    gw = win.game
    gw.new_game(seed=12)
    gw.on_reveal(40)
    i = next(k for k in range(gw.game.n) if not gw.game.open[k])
    gw.on_flag(i)
    gw.change("show_thoughts", True)
    assert wait(app, lambda: gw.probs is not None)
    assert gw.play.board.cells[i] == FLAG and gw.probs[i] is not None
    gw.change("show_thoughts", False)


def test_presets_and_custom(app, win):
    gw = win.game
    gw.change("preset", "expert")
    assert (gw.game.width, gw.game.height, gw.game.mines) == (30, 16, 99)
    gw.change("preset", "custom")
    gw.change("custom_w", 5)
    gw.change("custom_h", 4)
    gw.change("custom_m", 200)
    assert (gw.game.width, gw.game.height, gw.game.mines) == (5, 4, 19)
    assert gw.play.custom.isVisibleTo(gw.play)
    gw.change("preset", "beginner")
    assert not gw.play.custom.isVisibleTo(gw.play)


def test_first_click_rule_and_no_guess_settings(app, win):
    gw = win.game
    gw.change("first_click", "safe")
    assert gw.game.first_click == "safe"
    gw.change("no_guess", True)
    gw.new_game(seed=13)
    gw.on_reveal(40)
    end = time.time() + 5                    # раскладка без угадываний - в потоке (проверка 17.10)
    while gw.layout_pending is not None and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    assert gw.game.no_guess_ok
    gw.change("no_guess", False)
    gw.change("first_click", "opening")


def test_theme_and_language_on_the_fly(app, win):
    gw = win.game
    gw.ctx.set_lang("en")
    assert gw.play.new_button.text() == EN["new_game"]
    assert win.windowTitle().startswith("Minesweeper")
    gw.ctx.set_theme("light")
    assert gw.play.board.theme_name == "light"
    gw.ctx.set_lang("ru")
    gw.ctx.set_theme("dark")
    assert gw.play.new_button.text() == RU["new_game"]


def test_stats_and_settings_pages(app, win):
    gw = win.game
    gw.new_game(seed=14)
    win_by_hand(gw)
    gw.show_page("stats")
    assert gw.stats.table.rowCount() == 1
    gw.show_page("settings")
    assert gw.current_page() == "settings"
    gw.show_page("play")


def test_settings_survive_reopen(app, tmp_path):
    from aikit.host import make_window
    root = str(tmp_path / "home2")
    w, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    w.game.change("preset", "intermediate")
    w.game.change("ai_level", "novice")
    w.game.shutdown()
    w.close()
    w2, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    assert w2.game.settings["preset"] == "intermediate" and w2.game.game.width == 16
    assert w2.game.play.ai_buttons["novice"].isChecked()
    w2.game.shutdown()
    w2.close()


def test_close_stops_threads_within_two_seconds(app, win):
    gw = win.game
    gw.change("preset", "expert")
    gw.change("mode", "ai")
    gw.new_game(seed=15)
    wait(app, lambda: gw.ai.busy(), 5)
    t0 = time.time()
    assert gw.shutdown()
    assert time.time() - t0 < 2.5


def test_wrapped_labels_not_clipped(app, win):
    gw = win.game
    gw.change("show_thoughts", True)
    app.processEvents()
    gw.play.fit_labels()
    for w in gw.play.side.findChildren(type(gw.play.thoughts_hint)):
        if w.wordWrap() and w.isVisible() and w.width() > 0:
            assert w.height() >= w.heightForWidth(w.width()) - 1, w.text()
    gw.change("show_thoughts", False)


def test_shutdown_waits_for_a_running_job(app):
    """Проверка 17.10: мутант «потоки не ждут» выживал - закон выше закрывает окно, когда ход
    ИИ на «Профи» уже посчитан (ходы быстрые), и ждать нечего. Здесь поток точно работает:
    shutdown обязан дождаться его конца (в пределах 2 секунд)."""
    from game.ui.ai_thread import AiController
    ai = AiController()
    ai._start(1, "move", lambda: time.sleep(0.4))
    assert ai.busy()
    assert ai.shutdown(2000)
    assert not ai.busy()
