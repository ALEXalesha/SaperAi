"""Стартовое меню и растянутые настройки (автор 17.10: у Сапёра меню не было вовсе; у каждой
игры меню своё; настройки не узкой колонкой у левого края, а на всю ширину, как статистика).

Законы:
- окно открывается меню, фон-поле живёт, пока меню на экране, и стоит, когда его нет;
- меню цело (ничего за краем, текст влезает, соседи не налезают) от минимального окна до 4K,
  в обеих темах, на обоих языках, с «Продолжить» и без;
- карточка настроек занимает почти всю ширину страницы на всех размерах;
- ИИ не играет, пока на экране меню (и не начинает, если режим выбран в меню);
- «Продолжить» возвращает ту же партию, «Назад»/Esc - туда, откуда пришли;
- выбор поля в меню не уводит из меню, но новая партия уже нужного размера;
- фон: всё поле открыто волной до затухания на любом размере окна.
"""
import time

import pytest
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES, Backdrop, fill_share, layout_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.ui import menu as M


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    w.game.change("speed_ms", 0)
    yield w
    w.game.shutdown()
    w.close()


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def sizes(win):
    out = []
    for w, h in SIZES:
        win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
        out.append((win.width(), win.height()))
    return out


def test_window_opens_with_the_menu_and_backdrop_lives_only_there(app, win):
    gw = win.game
    assert gw.current_page() == "menu"
    assert isinstance(gw.menu, Backdrop) and gw.menu.running()
    t0 = gw.menu.t
    pump(app, 0.2)
    assert gw.menu.t > t0
    gw.menu_play()
    assert gw.current_page() == "play"
    assert not gw.menu.running()
    t1 = gw.menu.t
    pump(app, 0.15)
    assert gw.menu.t == t1


def test_menu_has_its_own_style(app, win):
    """Своё меню, не общий шаблон: свой фон-поле, своя таблица стилей, кнопки-клетки."""
    gw = win.game
    assert isinstance(gw.menu, M.MineField)
    assert "saperPanel" in gw.menu.styleSheet() and "Bahnschrift" in gw.menu.styleSheet()
    assert all(isinstance(b, M.TileButton) for b in gw.menu.buttons)
    assert gw.menu.title.family == "Bahnschrift"


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_menu_is_whole_at_every_size(app, win, theme, lang):
    gw = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for progress in (False, True):
        if progress:
            gw.new_game(seed=3)
            gw.on_reveal(40)
            gw.show_page("menu")
            assert gw.in_progress() and gw.menu.new_button.isVisible()
        for w, h in SIZES:
            win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
            pump(app, 0.03)
            gw.menu.grab()
            assert layout_problems(gw.menu) == [], (theme, lang, progress, win.size())
            # поле за панелью видно: панель не больше половины окна
            assert gw.menu.panel.width() <= gw.menu.width() * 0.5 + 1, win.size()


def test_menu_scales_up_on_big_windows(app, win):
    gw = win.game
    win.resize(1280, 800)
    pump(app, 0.03)
    small = (gw.menu.panel.width(), gw.menu.title.px)
    win.resize(3840, 2160)
    pump(app, 0.03)
    assert gw.menu.panel.width() > small[0] * 1.8 and gw.menu.title.px > small[1] * 1.8


def test_settings_card_stretches_like_stats(app, win):
    gw = win.game
    gw.show_page("settings")
    for size in sizes(win):
        win.resize(*size)
        pump(app, 0.03)
        page = gw.settings_page
        assert fill_share(page.box, page) > 0.9, (size, page.box.width(), page.width())
        gw.show_page("stats")
        pump(app, 0.02)
        gw.show_page("settings")


def test_ai_does_not_play_behind_the_menu(app, win):
    gw = win.game
    gw.change("mode", "ai")                      # выбор в меню: партия новая, но меню остаётся
    assert gw.current_page() == "menu"
    pump(app, 0.6)
    assert gw.game.opened == 0
    gw.menu_play()
    assert gw.current_page() == "play"
    end = time.time() + 20
    while gw.game.opened == 0 and time.time() < end:
        app.processEvents()
        time.sleep(0.003)
    assert gw.game.opened > 0
    gw.paused = True                              # ход ИИ уже запрошен, ответа ещё нет
    pump(app, 0.3)
    gw.paused = False
    opened = gw.game.opened
    gw._step()
    gw.on_escape()                                # Esc с поля - в меню; ИИ стоит
    assert gw.current_page() == "menu"
    pump(app, 0.8)
    assert gw.game.opened == opened               # запоздалый ответ ИИ не применён
    assert not gw.step_timer.isActive()


def test_continue_returns_the_same_game(app, win):
    gw = win.game
    assert gw.menu.play_button.text() == "Играть" and not gw.menu.new_button.isVisible()
    gw.menu_play()
    game = gw.game
    gw.on_reveal(40)
    gw.on_escape()
    assert gw.menu.play_button.text() == "Продолжить" and gw.menu.new_button.isVisible()
    assert [b.digit for b in gw.menu.buttons] == [1, 2, 3, 4]
    gw.menu_play()
    assert gw.game is game and gw.current_page() == "play"
    gw.on_escape()
    gw.menu.new_button.click()
    assert gw.game is not game and gw.current_page() == "play"
    gw.on_escape()
    assert gw.menu.play_button.text() == "Играть"
    assert [b.digit for b in gw.menu.buttons if not b.isHidden()] == [1, 2, 3]


def test_back_goes_where_you_came_from(app, win):
    gw = win.game
    for start in ("menu", "play"):
        gw.show_page(start)
        for page, back in (("settings", gw.settings_page.back_button), ("stats", gw.stats.back_button)):
            gw.show_page(page)
            back.click()
            assert gw.current_page() == start
            gw.show_page(page)
            gw.on_escape()
            assert gw.current_page() == start
    gw.show_page("play")
    gw.play.menu_button.click()
    assert gw.current_page() == "menu"


def test_choosing_in_the_menu_stays_in_the_menu(app, win):
    gw = win.game
    gw.menu.seg["field"]["intermediate"].click()
    assert gw.current_page() == "menu"
    assert gw.settings["preset"] == "intermediate" and gw.game.width == 16
    assert "16×16" in gw.menu.tag.text()
    gw.show_page("settings")
    gw.settings_page.first_combo.setCurrentIndex(1)       # правило первого клика: страница та же
    assert gw.current_page() == "settings" and gw.settings["first_click"] == "safe"


def test_backdrop_board_is_deterministic_and_opens_fully_before_the_fade(app):
    for w, h in SIZES + ((3840, 700), (900, 2160)):
        c = max(26, round(h / 19))
        cols, rows = w // c + 2, h // c + 2
        a, b = M.menu_board(cols, rows, 5), M.menu_board(cols, rows, 5)
        assert a["mine"] == b["mine"] and a["when"] == b["when"]
        assert max(a["when"]) < M.PERIOD - 1.6, (w, h)
        sx, sy = a["start"]
        assert not any(a["mine"][(sy + dy) * cols + sx + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def test_frozen_frame_redraws_after_going_back_in_time(app, win):
    """set_time назад (кадры README) - картинка открытых клеток собирается заново."""
    gw = win.game
    gw.menu.set_time(9.0)
    gw.menu.grab()
    late = gw.menu._acc_i
    gw.menu.set_time(2.0)
    gw.menu.grab()
    assert gw.menu._acc_i < late
    gw.menu.set_time(None)
    assert gw.menu.running()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_side_panel_in_menu_style_and_whole(app, win, theme, lang):
    """Боковая панель поля - в стиле меню (автор 17.10: «боковые меню тоже разнообразить»)
    и цела на всех размерах, в обоих режимах, с «Мыслями ИИ»."""
    gw = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    side = gw.play.side.styleSheet()
    assert "Bahnschrift" in side and "border-radius: 0" in side
    assert M.palette(theme)["bg"] in gw.play.styleSheet()
    assert gw.play.board.field == M.palette(theme)      # клетки поля - цвета «полевой карты»
    gw.show_page("play")
    for mode, thoughts in (("human", False), ("ai", True), ("human", True)):
        gw.change("mode", mode)
        gw.change("show_thoughts", thoughts)
        if mode == "ai":
            gw.toggle_pause()
        for w, h in SIZES:
            win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
            pump(app, 0.03)
            gw.play.side.grab()
            body = gw.play.body
            assert body.width() <= gw.play.scroll.viewport().width(), win.size()
            assert layout_problems(body) == [], (mode, thoughts, win.size())
