"""Настройки и статистика в стиле «полевой карты» (aikit.skin, автор 17.10) и находки проверки 17.10:
клавиши партии только на поле, часы стоят вне поля, раскладка без угадываний не вешает окно,
победа первым кликом не рекорд, пустая статистика говорит словами."""
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES
from aikit.skin import DEFAULT, SkinPage, difference, page_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.core.board import NO_GUESS_SECONDS, Game
from game.ui.skin import SKIN


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    yield w
    w.game.shutdown()
    w.close()


def pump(app, seconds=0.05, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.003)
    return until() if until is not None else True


def started(gw):
    gw.change("preset", "expert")
    gw.new_game(seed=5)
    gw.on_reveal(gw.game.n // 2)
    assert gw.game.status == "playing"
    return gw.game


@pytest.mark.parametrize("page", ["menu", "stats", "settings"])
def test_hotkeys_work_only_on_the_field(app, win, page):
    """Проверка 17.10: H в меню молча помечала партию «с подсказкой», N в статистике бросала её,
    T в настройках включала «Мысли ИИ»."""
    gw = win.game
    gw.show_page("play")
    g = started(gw)
    gw.show_page(page)
    target = gw.pages[page]
    win.activateWindow()
    target.setFocus()
    pump(app, 0.02)
    for key in (Qt.Key.Key_H, Qt.Key.Key_N, Qt.Key.Key_T, Qt.Key.Key_F2):
        QTest.keyClick(target, key)
        pump(app, 0.02)
    assert gw.game is g and not gw.assisted and gw.settings["show_thoughts"] is False
    assert gw.current_page() == page
    gw.show_page("play")
    gw.play.setFocus()
    pump(app, 0.02)
    QTest.keyClick(gw.play, Qt.Key.Key_N)        # на поле N - новая партия (клавиши вообще доходят)
    pump(app, 0.02)
    assert gw.game is not g


def test_clock_stops_off_the_field(app, win):
    """Проверка 17.10: начал партию, 3 с в меню - часы ушли с 0,1 на 3,2 с."""
    gw = win.game
    gw.show_page("play")
    g = started(gw)
    now = [100.0]
    g.clock = lambda: now[0]
    g.started = 100.0
    now[0] = 101.0
    gw.show_page("menu")
    now[0] = 500.0                               # долго в меню
    assert g.elapsed() == pytest.approx(1.0)
    gw.show_page("stats")
    gw.show_page("settings")
    now[0] = 900.0
    gw.menu_play()                               # «Продолжить»
    assert gw.current_page() == "play"
    now[0] = 902.0
    assert g.elapsed() == pytest.approx(3.0)
    win.game.pause()                             # вкладка оболочки скрыта
    now[0] = 2000.0
    win.game.resume()
    assert g.elapsed() == pytest.approx(3.0)


def test_no_guess_budget_on_dense_board():
    """Своё 60x60 с 1500 минами: перебор раскладок не дольше предела, честное «не вышло»."""
    g = Game(60, 60, 1500, seed=1, no_guess=True)
    t0 = time.monotonic()
    mine, ok = g.no_guess_layout(1830)
    spent = time.monotonic() - t0
    assert spent < NO_GUESS_SECONDS + 1.0, spent
    assert ok is False and sum(mine) == 1500
    stop = [False]
    t0 = time.monotonic()
    g.no_guess_layout(1830, cancel=lambda: stop[0] or (time.monotonic() - t0 > 0.2 and not stop.__setitem__(0, True)))
    assert time.monotonic() - t0 < 1.0


def test_no_guess_layout_does_not_freeze_the_window(app, win):
    """Проверка 17.10: первый клик на плотном своём поле «без угадываний» вешал окно на 20-50 с."""
    gw = win.game
    gw.change("preset", "custom")
    gw.change("custom_w", 60)
    gw.change("custom_h", 60)
    gw.change("custom_m", 1500)
    gw.change("no_guess", True)
    gw.show_page("play")
    t0 = time.monotonic()
    gw.on_reveal(1830)
    assert time.monotonic() - t0 < 0.5           # клик вернулся сразу, раскладка - в потоке
    assert gw.layout_pending is not None and gw.message == gw.t("no_guess_wait")
    assert gw.play.substatus.text() == gw.t("no_guess_wait")
    gw.on_reveal(5)                              # пока раскладывается - клики не идут
    assert pump(app, NO_GUESS_SECONDS + 3, lambda: gw.layout_pending is None)
    assert gw.game.status in ("playing", "won", "lost") and gw.game.no_guess_ok is False
    assert gw.t("no_guess_failed") in gw.play.substatus.text()
    assert gw.game.open[1830]
    gw.change("no_guess", False)


def test_no_guess_on_normal_board_still_works(app, win):
    gw = win.game
    gw.change("first_click", "safe")
    gw.change("no_guess", True)
    gw.new_game(seed=13)
    gw.on_reveal(40)
    assert pump(app, 5, lambda: gw.layout_pending is None)
    assert gw.game.no_guess_ok and gw.game.open[40]


def test_closing_during_layout_stops_the_thread(app, win):
    gw = win.game
    gw.change("preset", "custom")
    gw.change("custom_w", 60)
    gw.change("custom_h", 60)
    gw.change("custom_m", 1500)
    gw.change("no_guess", True)
    gw.show_page("play")
    gw.on_reveal(1830)
    t0 = time.monotonic()
    assert gw.shutdown() is True
    assert time.monotonic() - t0 < 2.0


def test_first_click_win_is_not_a_record(app, win):
    """Проверка 17.10: своё 2x2 с 3 минами - «победа» первым кликом и рекорд 0,0 с."""
    gw = win.game
    gw.change("preset", "custom")
    gw.change("custom_w", 2)
    gw.change("custom_h", 2)
    gw.change("custom_m", 3)
    gw.show_page("play")
    gw.new_game(seed=3)
    gw.on_reveal(0)
    assert gw.game.status == "won"
    assert gw.ctx.stats.totals()["games"] == 0 and gw.records() == {}
    assert gw.message == gw.t("first_click_win")


def test_empty_stats_say_so(app, win):
    gw = win.game
    gw.show_page("stats")
    st = gw.stats
    assert st.empty_note.isVisibleTo(st) and not st.table.isVisibleTo(st)
    assert st.empty_note.text() == gw.t("no_games_yet")


def test_side_lcd_counters(app, win):
    gw = win.game
    for theme in ("dark", "light"):
        win.ctx.set_theme(theme)
        assert "QLabel#bigNumber" in gw.play.side.styleSheet() and "#ff" in gw.play.side.styleSheet()
    gw.show_page("play")
    pump(app)
    img = gw.play.mines_value.grab().toImage()
    back = img.pixelColor(img.width() - 6, img.height() // 2)
    assert back.lightness() < 60                 # тёмное окошко табло и в светлой теме


def test_pages_look_like_the_field_not_like_aikit(app, win):
    gw = win.game
    assert isinstance(gw.stats, SkinPage) and isinstance(gw.settings_page, SkinPage)
    assert gw.stats.skin is SKIN and gw.settings_page.skin is SKIN
    assert SKIN.signature() != DEFAULT.signature()
    for name in ("stats", "settings"):
        gw.show_page(name)
        pump(app)
        page = gw.pages[name]
        own = page.grab()
        page.skin = DEFAULT                      # та же страница общим видом aikit
        page.set_theme("dark")
        pump(app)
        plain = page.grab()
        page.skin = SKIN
        page.set_theme("dark")
        assert difference(own, plain) > 0.3, name
    charts = gw.stats.charts.charts()
    assert all(c.skin is SKIN for c in charts)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_pages_clean_from_narrow_to_4k(app, win, theme, lang):
    """aikit.skin.page_problems во всех размерах: не обрезано, не за краем, не налезает."""
    gw = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for name in ("stats", "settings"):
        gw.show_page(name)
        for w, h in SIZES:
            win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
            pump(app, 0.03)
            assert page_problems(gw.pages[name]) == [], (name, w, h)


def test_settings_groups_and_tag(app, win):
    gw = win.game
    gw.show_page("settings")
    sp = gw.settings_page
    assert [g.text() for g in sp.box.groups] == [gw.t("group_view").upper(), gw.t("group_field").upper()]
    assert set(sp.rows) == {"theme", "language", "volume", "first_click", "no_guess"}
    assert sp.tag.text() == gw.t("settings_tag")
    gw.show_page("stats")
    assert gw.stats.tag.text().startswith(gw.t("menu_tag", w=9, h=9, m=10)[:4])
