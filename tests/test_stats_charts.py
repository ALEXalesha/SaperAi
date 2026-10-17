"""Графики статистики из общего aikit.charts (правило автора 10.10 - графики во всех играх с ИИ).

Законы: на странице статистики графики aikit; партия без подсказок пишется в журнал (поле,
итог, время; время победы - только у победы), показ ИИ и партия с подсказкой - нет; без
партий и с одной - заглушки словами; подписи целы (chart.clipped пуст) в обеих темах, на
обоих языках, в широком и самом узком окне; рекорд времени - лучшее (меньшее) время побед."""
from aikit.charts import ChartCard, all_charts
from tests.test_ui import app, win, win_by_hand  # noqa: F401 - фикстуры окна


def lose_by_hand(gw):
    g = gw.game
    if g.mine is None:
        gw.on_reveal(g.n // 2)
    gw.on_reveal(next(i for i in range(g.n) if g.mine[i]))


def labels_intact(app, win, gw):
    for theme in ("dark", "light"):
        for lang in ("ru", "en"):
            win.ctx.set_theme(theme)
            win.ctx.set_lang(lang)
            for width in (1400, 3840, win.minimumWidth()):
                win.resize(width, 820)
                app.processEvents()
                for c in all_charts(gw.stats):
                    c.grab()
                    assert c.clipped == [], (theme, lang, width, c.title, c.clipped)
                    assert c.overlaps() == [], (theme, lang, width, c.title, c.overlaps())
                    assert c.theme == theme
    win.ctx.set_theme("dark")
    win.ctx.set_lang("ru")


def test_charts_are_aikit_and_stubs_without_games(app, win):
    gw = win.game
    gw.show_page("stats")
    charts = all_charts(gw.stats)
    assert len(charts) >= 5 and all(isinstance(c, ChartCard) for c in charts)
    ch = gw.stats.charts
    for c in (ch.share, ch.by_level, ch.length, ch.records):
        c.grab()
        assert c.shown_empty and c.empty_text, c.title
    ch.passport.grab()
    assert not ch.passport.shown_empty                    # паспорт есть и без партий
    labels_intact(app, win, gw)


def test_games_go_to_the_log_and_charts(app, win):
    gw = win.game
    for seed, seconds, won in ((3, 50, True), (4, 30, False), (5, 20, True)):
        gw.new_game(seed=seed)
        gw.on_reveal(gw.game.n // 2)                  # первый клик: часы пошли
        gw.game.started -= seconds                    # партия шла seconds секунд
        win_by_hand(gw) if won else lose_by_hand(gw)
    games = gw.history.games
    assert [g["outcome"] for g in games] == ["win", "loss", "win"]
    assert all(g["level"] == "beginner" and g["seconds"] >= 0 for g in games)
    assert "win_time" in games[0] and "win_time" not in games[1]
    gw.show_page("stats")
    ch = gw.stats.charts
    for c in (ch.share, ch.by_level, ch.length, ch.records):
        c.grab()
        assert not c.shown_empty, c.title
    wins = [g["win_time"] for g in games if "win_time" in g]
    assert [y for _, y in ch.records.second] == [min(wins[:i + 1]) for i in range(len(wins))]
    labels_intact(app, win, gw)


def test_hint_and_ai_games_stay_out_of_the_log(app, win):
    gw = win.game
    gw.new_game(seed=3)
    gw.on_hint()
    win_by_hand(gw)
    assert gw.history.games == []


def test_win_time_record_is_the_lowest_time(app, win):
    gw = win.game
    for seed, seconds in ((3, 50), (5, 20), (6, 35)):
        gw.new_game(seed=seed)
        gw.on_reveal(gw.game.n // 2)
        gw.game.started -= seconds
        win_by_hand(gw)
    gw.show_page("stats")
    best = [y for _, y in gw.stats.charts.records.second]
    assert [round(v) for v in best] == [50, 20, 20]


def test_time_and_record_are_for_the_field_from_settings(app, win):
    """Проверка графиков 17.10: время партии и рекорд времени шли по всем полям сразу - после
    побед на «Новичке» за секунды рекорд на «Профи» показывал те же секунды. Теперь оба
    графика - по полю из настроек, его имя в заголовке (в таблице «Ваши партии» лучшее время
    тоже своё у каждого поля)."""
    import json
    gw = win.game
    games = [{"n": 1, "level": "beginner", "outcome": "win", "seconds": 5.0, "win_time": 5.0},
             {"n": 2, "level": "expert", "outcome": "win", "seconds": 120.0, "win_time": 120.0},
             {"n": 3, "level": "beginner", "outcome": "loss", "seconds": 2.0},
             {"n": 4, "level": "expert", "outcome": "loss", "seconds": 40.0},
             {"n": 5, "level": "expert", "outcome": "win", "seconds": 100.0, "win_time": 100.0}]
    with open(gw.ctx.file("games.json"), "w", encoding="utf-8") as f:
        json.dump({"next": 6, "games": games}, f)
    from aikit import gamelog
    gw.history = gamelog.GameLog(gw.ctx.file("games.json"))
    gw.change("preset", "expert")
    gw.show_page("stats")
    ch = gw.stats.charts
    assert [y for _, y in ch.length.points] == [120.0, 40.0, 100.0]
    assert [y for _, y in ch.records.points] == [120.0, 100.0]
    assert [y for _, y in ch.records.second] == [120.0, 100.0]
    assert gw.t("expert") in ch.length.title and gw.t("expert") in ch.records.title
    gw.change("preset", "beginner")
    gw.show_page("stats")
    assert [y for _, y in ch.records.second] in ([5.0], [])
    assert gw.t("beginner") in ch.records.title
    labels_intact(app, win, gw)
