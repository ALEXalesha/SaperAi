"""Виджет игры (create_widget по контракту): поле, боковая панель, статистика, настройки.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir.

Рекорды честные: партия с подсказкой или включёнными «Мыслями ИИ» (assisted) в статистику и
рекорды не идёт, партия «ИИ играет сам» - тем более.
"""
import gc
import random

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QScrollArea, QSlider, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import gamelog, theme
from aikit.charts import GameCharts
from aikit.storage import load_json, save_json
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai.agents import LEVELS as AI_LEVELS
from game.core.board import LEVELS, MAX_SIDE, Game, check_size
from game.ui.ai_thread import AiController
from game.ui.board_view import BoardView
from game.ui.i18n import translator
from game.ui.menu import MenuPage, page_qss, side_qss
from game.ui.menu import palette as menu_palette
from game.version import VERSION

PRESETS = ("beginner", "intermediate", "expert", "custom")
SCHEMA = {
    "preset": ("beginner", st.choice(*PRESETS)),
    "custom_w": (20, st.int_range(2, MAX_SIDE)),
    "custom_h": (12, st.int_range(2, MAX_SIDE)),
    "custom_m": (35, st.int_range(1, MAX_SIDE * MAX_SIDE - 1)),
    "first_click": ("opening", st.choice("opening", "safe")),
    "no_guess": (False, st.boolean()),
    "ai_level": ("strong", st.choice(*AI_LEVELS)),
    "mode": ("human", st.choice("human", "ai")),
    "show_thoughts": (False, st.boolean()),
    "speed_ms": (250, st.int_range(0, 1500)),
}
RECORDS_KEEP = 5


def page_widget():
    w = QWidget()
    w.setObjectName("page")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return w


def fmt_clock(seconds):
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else str(s)


def fmt_time(t, seconds):
    if seconds < 90:
        return t("seconds", n=round(seconds))
    if seconds < 5400:
        return t("minutes", n=round(seconds / 60))
    return t("hours", n=f"{seconds / 3600:.1f}")


def number(n):
    return f"{n:,}".replace(",", " ")


def scroll_page(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(widget)
    return scroll


# --- партия ---


class PlayPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)
        self.board = BoardView()
        self.board.revealAt.connect(gw.on_reveal)
        self.board.flagAt.connect(gw.on_flag)
        self.board.chordAt.connect(gw.on_chord)
        root.addWidget(self.board, 1)

        side = card()
        side.setFixedWidth(330)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QWidget()
        self.body = body
        scroll = scroll_page(body)
        self.scroll = scroll
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        outer.addWidget(scroll)
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(7)
        self.heading = label("", "section")
        col.addWidget(self.heading)

        nums = QHBoxLayout()
        self.mines_caption, self.mines_value = label("", "hint"), label("0", "bigNumber")
        self.time_caption, self.time_value = label("", "hint"), label("0", "bigNumber")
        for cap, val in ((self.mines_caption, self.mines_value), (self.time_caption, self.time_value)):
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(cap)
            box.addWidget(val)
            nums.addLayout(box, 1)
        col.addLayout(nums)
        self.status = label("", "status", wrap=True)
        col.addWidget(self.status)
        self.substatus = label("", "muted", wrap=True)
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.substatus)
        self.new_button = button("", "primary", lambda: gw.new_game())
        col.addWidget(self.new_button)

        self.level_caption = label("", "muted")
        col.addWidget(self.level_caption)
        self.preset = Combo()
        for k in PRESETS:
            self.preset.addItem("", k)
        self.preset.currentIndexChanged.connect(lambda i: gw.change("preset", self.preset.itemData(i)))
        col.addWidget(self.preset)
        self.custom = QWidget()
        cg = QGridLayout(self.custom)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setHorizontalSpacing(6)
        self.spins = {}
        self.spin_captions = {}
        for c, (key, lo, hi) in enumerate((("custom_w", 2, MAX_SIDE), ("custom_h", 2, MAX_SIDE),
                                           ("custom_m", 1, MAX_SIDE * MAX_SIDE - 1))):
            cap = label("", "hint")
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.valueChanged.connect(lambda v, k=key: gw.change(k, int(v)))
            cg.addWidget(cap, 0, c)
            cg.addWidget(sp, 1, c)
            self.spins[key] = sp
            self.spin_captions[key] = cap
        col.addWidget(self.custom)

        self.mode_caption = label("", "muted")
        col.addWidget(self.mode_caption)
        w, self.mode_buttons = segmented({"human": "", "ai": ""}, lambda v: gw.change("mode", v))
        col.addWidget(w)
        self.ai_caption = label("", "muted")
        col.addWidget(self.ai_caption)
        w, self.ai_buttons = segmented({lv: "" for lv in AI_LEVELS}, lambda v: gw.change("ai_level", v))
        col.addWidget(w)
        self.speed_caption = label("", "hint")
        col.addWidget(self.speed_caption)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 1500)
        self.speed.setInvertedAppearance(True)       # вправо - быстрее (меньше пауза)
        self.speed.valueChanged.connect(lambda v: gw.change("speed_ms", int(v)))
        col.addWidget(self.speed)
        self.pause_button = button("", None, gw.toggle_pause)
        col.addWidget(self.pause_button)
        self.hint_button = button("", None, gw.on_hint)
        col.addWidget(self.hint_button)
        self.thoughts_box = QCheckBox("")
        self.thoughts_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts_box.toggled.connect(lambda on: gw.change("show_thoughts", on))
        col.addWidget(self.thoughts_box)
        self.thoughts_hint = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_hint)
        self.thoughts_source = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_source)
        self.assisted_note = label("", "hint", wrap=True)
        col.addWidget(self.assisted_note)
        col.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        col.addWidget(self.menu_button)
        last = QHBoxLayout()
        self.stats_button = button("", None, lambda: gw.show_page("stats"))
        self.settings_button = button("", None, lambda: gw.show_page("settings"))
        last.addWidget(self.stats_button, 1)
        last.addWidget(self.settings_button, 1)
        col.addLayout(last)
        self.foot = label("", "hint", wrap=True)
        col.addWidget(self.foot)
        root.addWidget(side)
        self.side = side

    def fit_labels(self):
        """Подписи с переносом получают высоту по своей ширине (qt-wrapped-label-height:
        высоту не фиксировать, только минимум)."""
        for w in self.side.findChildren(QLabel):
            if w.wordWrap() and w.width() > 0:
                w.setMinimumHeight(w.heightForWidth(w.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_labels()

    def sync(self, s):
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(self.preset.findData(s["preset"]))
        self.preset.blockSignals(False)
        self.custom.setVisible(s["preset"] == "custom")
        for key, sp in self.spins.items():
            sp.blockSignals(True)
            sp.setValue(s[key])
            sp.blockSignals(False)
        self.mode_buttons[s["mode"]].setChecked(True)
        self.ai_buttons[s["ai_level"]].setChecked(True)
        from game.ai.net import default_net
        self.ai_buttons["medium"].setEnabled(default_net() is not None)
        self.speed.blockSignals(True)
        self.speed.setValue(s["speed_ms"])
        self.speed.blockSignals(False)
        self.speed.setVisible(s["mode"] == "ai")
        self.speed_caption.setVisible(s["mode"] == "ai")
        self.pause_button.setVisible(s["mode"] == "ai")
        self.thoughts_box.blockSignals(True)
        self.thoughts_box.setChecked(s["show_thoughts"])
        self.thoughts_box.blockSignals(False)

    def retranslate(self):
        t = self.gw.t
        self.heading.setText(t("app_title"))
        self.mines_caption.setText(t("mines_left"))
        self.time_caption.setText(t("time"))
        self.new_button.setText(t("new_game"))
        self.level_caption.setText(t("level_caption"))
        for i, k in enumerate(PRESETS):
            if k == "custom":
                self.preset.setItemText(i, t(k))
            else:
                w, h, m = LEVELS[k]
                self.preset.setItemText(i, f"{t(k)} · {w}×{h} · {m}")
        for key, word in (("custom_w", "width"), ("custom_h", "height"), ("custom_m", "mines")):
            self.spin_captions[key].setText(t(word))
        self.mode_caption.setText(t("mode"))
        self.mode_buttons["human"].setText(t("mode_human"))
        self.mode_buttons["ai"].setText(t("mode_ai"))
        self.ai_caption.setText(t("ai_level"))
        for k, b in self.ai_buttons.items():
            b.setText(t("ai_" + k))
        self.speed_caption.setText(t("speed"))
        self.hint_button.setText(t("hint"))
        self.pause_button.setText(t("resume") if self.gw.paused else t("pause"))
        self.thoughts_box.setText(t("thoughts"))
        self.thoughts_hint.setText(t("thoughts_hint"))
        self.assisted_note.setText(t("assisted"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.menu_button.setText(t("to_menu"))
        self.foot.setText(t("footer", v=VERSION))
        self.fit_labels()


# --- статистика ---


def table_widget(cols):
    tw = QTableWidget(0, cols)
    tw.verticalHeader().setVisible(False)
    tw.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tw.setShowGrid(False)
    tw.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tw.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = tw.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    return tw


def fit_height(tw):
    tw.resizeRowsToContents()
    tw.setFixedHeight(tw.horizontalHeader().height() + sum(tw.rowHeight(r) for r in range(tw.rowCount())) + 4)


def item(text, align=Qt.AlignmentFlag.AlignCenter):
    it = QTableWidgetItem(text)
    it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return it


CHART_LEVELS = ("beginner", "intermediate", "expert", "custom")


class StatsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = page_widget()
        outer.addWidget(scroll_page(body))
        col = QVBoxLayout(body)
        col.setContentsMargins(26, 22, 26, 22)
        col.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.back_button = button("", None, lambda: gw.go_back())
        top.addWidget(self.back_button)
        col.addLayout(top)
        mine = card()
        mc = QVBoxLayout(mine)
        mc.setContentsMargins(18, 14, 18, 14)
        self.mine_title = label("", "section")
        mc.addWidget(self.mine_title)
        self.table = table_widget(6)
        mc.addWidget(self.table)
        col.addWidget(mine)
        # графики (правило автора 10.10 - графики в статистике всех игр с ИИ): доля побед,
        # итоги по полям, время партии, время победы с рекордом, сила ИИ по паспорту
        cc = card()
        cl = QVBoxLayout(cc)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)
        self.charts_title = label("", "section")
        cl.addWidget(self.charts_title)
        self.charts = GameCharts(CHART_LEVELS, length_key="seconds", score_key="win_time", score_better="min",
                                 passport=True)
        cl.addWidget(self.charts)
        col.addWidget(cc)
        pc = card()
        lay = QVBoxLayout(pc)
        lay.setContentsMargins(18, 14, 18, 14)
        self.pass_title = label("", "section")
        self.pass_text = label("", "muted", wrap=True)
        self.checks = table_widget(7)
        self.net_text = label("", "hint", wrap=True)
        for w in (self.pass_title, self.pass_text, self.checks, self.net_text):
            lay.addWidget(w)
        col.addWidget(pc)
        col.addStretch(1)

    def refresh(self):
        t = self.gw.t
        self.heading.setText(t("stats_title"))
        self.back_button.setText(t("back"))
        self.mine_title.setText(t("your_games"))
        self.table.setHorizontalHeaderLabels([t(k) for k in ("col_level", "col_games", "col_wins", "col_rate",
                                                               "col_best", "col_streak")])
        stats = self.gw.ctx.stats
        records = self.gw.records()
        rows = [k for k in sorted(stats.data) if stats.data[k]["games"]]
        self.table.setRowCount(len(rows))
        for r, key in enumerate(rows):
            e = stats.entry(key)
            best = records.get(key) or []
            self.table.setItem(r, 0, item(self.gw.key_title(key), Qt.AlignmentFlag.AlignLeft))
            self.table.setItem(r, 1, item(str(e["games"])))
            self.table.setItem(r, 2, item(str(e["wins"])))
            self.table.setItem(r, 3, item(f"{100 * e['wins'] / max(1, e['games']):.0f}%"))
            self.table.setItem(r, 4, item(f"{best[0]:.1f}" if best else "-"))
            self.table.setItem(r, 5, item(str(e["best_streak"])))
        fit_height(self.table)
        self.refresh_charts()
        self.pass_title.setText(t("passport"))
        try:
            from game.ai.net import load_passport
            pp = load_passport()
        except (OSError, ValueError):
            self.pass_text.setText(t("not_measured"))
            self.checks.hide()
            self.net_text.hide()
            return
        checks = pp["checks"]
        n = max((c["games"] for c in checks), default=0)
        self.pass_text.setText(t("passport_text", n=number(n)))
        heads = [t("col_ai")]
        cols = [(lv, rule) for lv in ("beginner", "intermediate", "expert") for rule in ("opening", "safe")]
        heads += [f"{t(lv)} · {t('rule_' + rule)}" for lv, rule in cols]
        self.checks.setHorizontalHeaderLabels(heads)
        by = {(c["agent"], c["level"], c["first_click"]): c for c in checks}
        agents = [a for a in AI_LEVELS if any(k[0] == a for k in by)]
        self.checks.setRowCount(len(agents))
        for r, a in enumerate(agents):
            self.checks.setItem(r, 0, item(t("ai_" + a), Qt.AlignmentFlag.AlignLeft))
            for c, key in enumerate(cols, start=1):
                ch = by.get((a,) + key)
                self.checks.setItem(r, c, item(f"{100 * ch['win_rate']:.1f}%" if ch else "-"))
        fit_height(self.checks)
        self.checks.show()
        net, tr = pp.get("network"), pp.get("training")
        if net and tr:
            self.net_text.setText(t("net_text", channels=net["channels"], depth=net["depth"],
                                    params=number(net["parameters"]),
                                    positions=number(tr.get("positions", 0)),
                                    time=fmt_time(t, tr.get("seconds", 0) + tr.get("data_seconds", 0))))
            self.net_text.show()
        else:
            self.net_text.hide()

    def refresh_charts(self):
        _refresh_charts(self)


def passport_bars(t, rule):
    """Столбики паспорта: поле - группа, уровень ИИ - серия, доля побед при правиле первого хода."""
    try:
        from game.ai.net import load_passport
        checks = load_passport()["checks"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    by = {(c["agent"], c["level"], c["first_click"]): c["win_rate"] for c in checks}
    levels = [lv for lv in ("beginner", "intermediate", "expert") if any(k[1] == lv for k in by)]
    agents = [a for a in AI_LEVELS if any(k[0] == a for k in by)]
    if not levels or not agents:
        return None
    keys = {"novice": "warn", "medium": "accent", "strong": "good"}
    return ([t(lv) for lv in levels],
            [(t("ai_" + a), keys.get(a, "accent"), [by.get((a, lv, rule), 0.0) for lv in levels]) for a in agents])


def _refresh_charts(page):
    t = page.gw.t
    page.charts_title.setText(t("charts"))
    page.charts.set_theme(page.gw.ctx.theme)
    unit = t("unit_s")
    page.charts.length.unit = unit
    page.charts.records.unit = unit
    rule = page.gw.settings["first_click"]
    field = page.gw.settings["preset"]
    games = page.gw.history.games
    ch = page.charts
    ch.refresh(games, page.gw.ctx.lang, {k: t(k) for k in CHART_LEVELS},
               labels={"share": t("ch_share"), "share_empty": t("ch_share_empty"),
                       "levels": t("ch_levels"), "levels_empty": t("ch_levels_empty"),
                       "length": t("ch_time", field=t(field)), "length_empty": t("ch_time_empty"),
                       "length_y": t("ch_seconds"),
                       "score": t("ch_win_time", field=t(field)), "score_empty": t("ch_win_time_empty"),
                       "score_y": t("ch_seconds"), "points": t("ch_win"),
                       "passport": t("ch_passport", rule=t("rule_" + rule))},
               passport=passport_bars(t, rule))
    # время и рекорд - только по полю из настроек: секунды «Новичка» и «Профи» не сравнить,
    # и рекорд по всем полям был бы рекордом самого лёгкого (как лучшее время в таблице)
    mine = [g for g in games if g["level"] == field]
    ch.length.set_points(gamelog.series(mine, "seconds"))
    ch.records.set_points(gamelog.series(mine, "win_time"), gamelog.best_curve(mine, "win_time", "min"))


# --- настройки ---


class SettingsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer0 = QVBoxLayout(self)
        outer0.setContentsMargins(0, 0, 0, 0)
        body = page_widget()
        outer0.addWidget(scroll_page(body))
        outer = QVBoxLayout(body)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.back_button = button("", None, lambda: gw.go_back())
        top.addWidget(self.back_button)
        outer.addLayout(top)
        # карточка на всю ширину страницы, как карточки статистики (автор 17.10: настройки
        # не должны стоять узкой колонкой у левого края); подписи - 3 части, поля - 2
        box = card()
        self.box = box
        self.grid = QGridLayout(box)
        self.grid.setContentsMargins(22, 18, 22, 18)
        self.grid.setHorizontalSpacing(22)
        self.grid.setVerticalSpacing(16)
        self.grid.setColumnStretch(0, 3)
        self.grid.setColumnStretch(1, 2)
        self.rows = {}
        self.theme_combo = Combo()
        for k in theme.THEMES:
            self.theme_combo.addItem("", k)
        self.theme_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_theme(self.theme_combo.itemData(i)))
        self._row("theme", self.theme_combo)
        self.lang_combo = Combo()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_lang(self.lang_combo.itemData(i)))
        self._row("language", self.lang_combo)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(gw.ctx.sound.volume)
        self.volume.valueChanged.connect(gw.ctx.set_volume)
        self._row("volume", self.volume)
        self.first_combo = Combo()
        self.first_combo.addItem("", "opening")
        self.first_combo.addItem("", "safe")
        self.first_combo.currentIndexChanged.connect(lambda i: gw.change("first_click", self.first_combo.itemData(i)))
        self._row("first_click", self.first_combo)
        self.no_guess_box = QCheckBox("")
        self.no_guess_box.toggled.connect(lambda on: gw.change("no_guess", on))
        self._row("no_guess", self.no_guess_box)
        outer.addWidget(box)
        self.note = label("", "hint")
        outer.addWidget(self.note)
        outer.addStretch(1)

    def _row(self, key, widget):
        r = len(self.rows)
        names = QVBoxLayout()
        names.setSpacing(2)
        title = label("", "section")
        hint = label("", "hint", wrap=True)
        names.addWidget(title)
        names.addWidget(hint)
        self.grid.addLayout(names, r, 0)
        self.grid.addWidget(widget, r, 1)
        self.rows[key] = (title, hint)

    def retranslate(self):
        t = self.gw.t
        self.heading.setText(t("settings_title"))
        self.back_button.setText(t("back"))
        for key, (title, hint) in self.rows.items():
            title.setText(t(key))
            hint.setText(t(key + "_hint"))
        for i, k in enumerate(theme.THEMES):
            self.theme_combo.setItemText(i, t(k))
        self.first_combo.setItemText(0, t("first_opening"))
        self.first_combo.setItemText(1, t("first_safe"))
        self.note.setText(t("saved_note"))
        self.sync()

    def sync(self):
        g = self.gw
        for combo, value in ((self.theme_combo, g.ctx.theme), (self.lang_combo, g.ctx.lang),
                             (self.first_combo, g.settings["first_click"])):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        self.no_guess_box.blockSignals(True)
        self.no_guess_box.setChecked(g.settings["no_guess"])
        self.no_guess_box.blockSignals(False)


# --- сам виджет игры ---


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        gc.freeze()          # полный проход сборщика посреди поиска держит GIL (урок ChessCheckersAi)
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.settings = st.Settings(SCHEMA, ctx.file("settings.json"))
        self.game = None
        self.token = 0
        self.rng = random.Random()
        self.mode = "human"          # кто играет в этой партии
        self.paused = False          # «ИИ играет сам» на паузе
        self.assisted = False
        self.recorded = False
        self.probs = None
        self.thoughts_info = None
        self.hint_cell = -1
        self.last_ai = -1
        self.message = ""
        self.ai = AiController(self)
        self.ai.ready.connect(self.on_ai)
        self.step_timer = QTimer(self)
        self.step_timer.setSingleShot(True)
        self.step_timer.timeout.connect(self._step)
        self.clock = QTimer(self)
        self.clock.setInterval(250)
        self.clock.timeout.connect(self._tick)
        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.back_page = "menu"
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.history = gamelog.GameLog(ctx.file("games.json"))
        self.stats = StatsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {"menu": self.menu, "play": self.play, "stats": self.stats, "settings": self.settings_page}
        for p in self.pages.values():
            self.stack.addWidget(p)
        for keys, slot in (("Escape", self.on_escape), ("F2", lambda: self.new_game()),
                           ("N", lambda: self.new_game()), ("H", self.on_hint),
                           ("T", lambda: self.change("show_thoughts", not self.settings["show_thoughts"]))):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        ctx.changed.connect(self.on_ctx_changed)
        self.apply_theme()
        self.retranslate()
        self.new_game(show=False)           # меню - первая страница стопки: окно открывается им

    def minimumSizeHint(self):
        return QSize(900, 640)

    # --- общее ---

    def current_page(self):
        w = self.stack.currentWidget()
        return next(k for k, p in self.pages.items() if p is w)

    def show_page(self, name):
        prev = self.current_page()
        if name in ("stats", "settings") and prev in ("menu", "play"):
            self.back_page = prev           # «Назад» и Esc - туда, откуда пришли
        self.stack.setCurrentWidget(self.pages[name])
        if name == "stats":
            self.stats.refresh()
        elif name == "settings":
            self.settings_page.sync()
        elif name == "menu":
            self.refresh_menu()
        if name == "play" and prev != "play":
            self.after_change(moved=False)  # ИИ и «Мысли ИИ» - снова, раз поле на экране
        elif name != "play" and prev == "play":
            self.token += 1                 # поле ушло с экрана: ИИ не играет за меню
            self.step_timer.stop()
            self.ai.cancel()

    def go_back(self):
        self.show_page(self.back_page)

    def on_escape(self):
        page = self.current_page()
        if page == "play":
            self.show_page("menu")
        elif page in ("stats", "settings"):
            self.go_back()

    def in_progress(self):
        """Партия начата и не кончена - в меню «Продолжить» и «Новая игра»."""
        return self.game is not None and self.game.status == "playing"

    def menu_play(self):
        if self.in_progress():
            self.show_page("play")
        else:
            self.new_game()

    def refresh_menu(self):
        if not hasattr(self, "menu"):
            return
        t = self.t
        w, h, m = self.size_now()
        totals = self.ctx.stats.totals()
        best = self.records().get(self.stats_key()) or []
        name = t(self.settings["preset"])
        foot = t("menu_foot", games=totals["games"], wins=totals["wins"])
        foot += " · " + (t("menu_best", field=name, s=f"{best[0]:.1f}") if best else t("menu_no_best", field=name))
        self.menu.set_info(t("menu_tag", w=w, h=h, m=m), foot, t("menu_version", v=VERSION))
        self.menu.sync(self.settings, self.in_progress())

    def size_now(self):
        s = self.settings
        if s["preset"] == "custom":
            w, h, m = s["custom_w"], s["custom_h"], s["custom_m"]
            return w, h, min(m, w * h - 1)
        return LEVELS[s["preset"]]

    def stats_key(self):
        s = self.settings
        key = f"{s['preset']}/{s['first_click']}"
        if s["preset"] == "custom":
            w, h, m = self.size_now()
            key = f"custom-{w}x{h}-{m}/{s['first_click']}"
        return key + ("/ng" if s["no_guess"] else "")

    def key_title(self, key):
        parts = key.split("/")
        name = parts[0]
        if name.startswith("custom-"):
            title = f"{self.t('custom')} {name[7:].replace('x', '×').replace('-', ' · ')}"
        else:
            title = self.t(name)
        title += " · " + self.t("rule_" + parts[1])
        if len(parts) > 2:
            title += " · " + self.t("no_guess")
        return title

    def change(self, key, value):
        if self.settings[key] == value:
            return
        self.settings.set(key, value)
        self.play.sync(self.settings)
        self.settings_page.sync()
        if key in ("preset", "custom_w", "custom_h", "custom_m", "first_click", "no_guess", "mode"):
            # новая партия, но страница та же: выбор поля в меню или правила в настройках не
            # уводят на поле (раньше смена правила первого клика в настройках уводила)
            self.new_game(show=self.current_page() == "play")
        elif key == "ai_level":
            self.probs = None
            self.after_change(moved=False)
        elif key == "show_thoughts":
            if value and self.mode == "human" and self.game is not None and self.game.status == "playing":
                self.assisted = True
            self.probs = None
            self.after_change(moved=False)
        elif key == "speed_ms" and self.mode == "ai" and self.step_timer.isActive():
            self.step_timer.start(value)

    def on_ctx_changed(self, what):
        if what == "theme":
            self.apply_theme()
        elif what == "lang":
            self.t = translator(self.ctx.lang)
            self.retranslate()

    def apply_theme(self):
        c = theme.palette(self.ctx.theme)
        self.menu.set_theme(self.ctx.theme)
        # боковая панель и фон поля - в стиле меню (автор 17.10: и боковые панели у игр свои)
        self.play.side.setStyleSheet(side_qss(menu_palette(self.ctx.theme)))
        self.play.setStyleSheet(page_qss(menu_palette(self.ctx.theme)))
        self.play.board.set_theme(self.ctx.theme, menu_palette(self.ctx.theme))
        self.stats.charts.set_theme(self.ctx.theme)
        for combo in self.findChildren(Combo):
            combo.set_arrow_color(c["text"])
        self.update()

    def retranslate(self):
        self.menu.retranslate(self.in_progress())
        self.play.retranslate()
        self.settings_page.retranslate()
        if self.current_page() == "stats":
            self.stats.refresh()
        self.refresh()

    def shutdown(self):
        """Окно закрывается: таймеры стоп, потоки ИИ дождаться (не дольше 2 с)."""
        self._invalidate()
        self.clock.stop()
        return self.ai.shutdown(2000)

    def _invalidate(self):
        self.token += 1
        self.step_timer.stop()
        self.ai.cancel()

    # --- партия ---

    def new_game(self, seed=None, show=True):
        s = self.settings
        w, h, m = self.size_now()
        check_size(w, h, m)
        if seed is None:
            seed = self.rng.randrange(2 ** 31)
        self._invalidate()
        self.game = Game(w, h, m, seed=seed, first_click=s["first_click"], no_guess=s["no_guess"])
        self.mode = s["mode"]
        self.paused = False
        self.play.pause_button.setText(self.t("pause"))
        self.assisted = self.mode == "human" and s["show_thoughts"]
        self.recorded = False
        self.probs = None
        self.thoughts_info = None
        self.hint_cell = -1
        self.last_ai = -1
        self.message = ""
        if show:
            self.stack.setCurrentWidget(self.play)
        self.play.sync(s)
        self.after_change()
        self.refresh_menu()

    def human_can_move(self):
        return self.mode == "human" and self.game is not None and not self.game.over

    def on_reveal(self, i):
        if not self.human_can_move():
            return
        opened = self.game.reveal(i)
        if opened or self.game.over:
            self.ctx.sound.play("move")
            self.after_change()

    def on_flag(self, i):
        if not self.human_can_move():
            return
        if self.game.toggle_flag(i):
            self.ctx.sound.play("capture")
            self.after_change(moved=False)

    def on_chord(self, i):
        if not self.human_can_move():
            return
        opened = self.game.chord(i)
        if opened or self.game.over:
            self.ctx.sound.play("move")
            self.after_change()

    def on_hint(self):
        if not self.human_can_move():
            return
        self.assisted = True
        self.ai.request_hint(self.token, self.game.observe())

    def after_change(self, moved=True):
        """После хода: перерисовать, записать итог, запустить ИИ или «Мысли ИИ»."""
        self.token += 1
        self.step_timer.stop()
        self.ai.cancel()
        g = self.game
        if moved:
            self.hint_cell = -1
            self.probs = None
        if g.over:
            self.probs = None
            self.clock.stop()
            self._finish()
        else:
            if g.started is not None:
                self.clock.start()
            on_screen = self.current_page() == "play"
            if self.settings["show_thoughts"] and on_screen:
                self.ai.request_thoughts(self.token, g.observe(), self.settings["ai_level"])
            if self.mode == "ai" and not self.paused and on_screen:
                self.step_timer.start(self.settings["speed_ms"])
        self.refresh()

    def toggle_pause(self):
        """Пауза «ИИ играет сам»: можно рассмотреть поле и «Мысли ИИ»."""
        if self.mode != "ai":
            return
        self.paused = not self.paused
        self.play.pause_button.setText(self.t("resume") if self.paused else self.t("pause"))
        self.after_change(moved=False)

    def _step(self):
        g = self.game
        if g is None or g.over or self.mode != "ai":
            return
        self.ai.request_move(self.token, g.observe(), self.settings["ai_level"], self.rng.randrange(2 ** 31))

    def on_ai(self, token, kind, payload):
        if token != self.token or self.game is None:
            return
        if isinstance(payload, Exception):
            self.message = self.t("error", e=payload)
            self.refresh()
            return
        if kind == "thoughts":
            self.probs = payload["probs"]
            self.thoughts_info = payload
            self.refresh()
        elif kind == "hint":
            self.hint_cell = payload["cell"]
            self.message = self.t("hint_safe") if payload["safe"] else \
                self.t("hint_guess", p=f"{100 * payload['p']:.1f}")
            self.refresh()
        elif kind == "move" and self.mode == "ai" and not self.game.over:
            mv = payload
            for i in mv.cells:
                self.game.reveal(i)
                if self.game.over:
                    break
            self.last_ai = mv.cells[-1] if mv.cells else -1
            if mv.probs is not None and mv.exact and not self.game.over:
                # точные мины (вероятность ровно 1) ИИ помечает флажком - счётчик мин честный
                for i, q in enumerate(mv.probs):
                    if q == 1.0 and not self.game.flag[i] and not self.game.open[i]:
                        self.game.toggle_flag(i)
            if mv.guess and mv.risk == mv.risk:          # nan у новичка - риск не считал
                self.message = self.t("ai_guess", p=f"{100 * mv.risk:.1f}")
            elif not mv.guess:
                self.message = self.t("ai_safe", n=len(mv.cells))
            else:
                self.message = ""
            self.ctx.sound.play("move")
            self.after_change()

    def _finish(self):
        g = self.game
        if self.recorded:
            return
        self.recorded = True
        won = g.status == "won"
        self.ctx.sound.play("win" if won else "loss")
        if self.mode != "human" or self.assisted:
            return
        key = self.stats_key()
        self.ctx.stats.record(key, "win" if won else "loss")
        game = {"level": self.settings["preset"], "outcome": "win" if won else "loss",
                "seconds": round(g.elapsed(), 2)}
        if won:
            game["win_time"] = game["seconds"]
        self.history.record(game)                       # журнал для графиков статистики
        if won:
            recs = self.records()
            best = sorted((recs.get(key) or []) + [round(g.elapsed(), 2)])[:RECORDS_KEEP]
            recs[key] = best
            save_json(self.ctx.file("records.json"), recs)

    def records(self):
        data = load_json(self.ctx.file("records.json"))
        if not isinstance(data, dict):
            return {}
        out = {}
        for k, v in data.items():
            if isinstance(v, list) and all(isinstance(x, (int, float)) and x >= 0 for x in v):
                out[k] = sorted(v)[:RECORDS_KEEP]
        return out

    # --- вид ---

    def _tick(self):
        if self.game is not None:
            self.play.time_value.setText(fmt_clock(self.game.elapsed()))
            if self.game.over:
                self.clock.stop()

    def refresh(self):
        g = self.game
        if g is None:
            return
        t = self.t
        pp = self.play
        show = self.settings["show_thoughts"] and not g.over
        pp.board.set_board(g.width, g.height, g.view(), self.probs if show else None,
                           self.hint_cell, self.last_ai if self.mode == "ai" else -1)
        pp.board.enabled_input = self.mode == "human"
        pp.mines_value.setText(str(g.mines_left()))
        pp.time_value.setText(fmt_clock(g.elapsed()))
        ai_name = t("ai_" + self.settings["ai_level"])
        if g.status == "won":
            restyle(pp.status, "statusWin")
            pp.status.setText(t("status_ai_won") if self.mode == "ai" else t("status_won"))
        elif g.status == "lost":
            restyle(pp.status, "statusLoss")
            pp.status.setText(t("status_ai_lost") if self.mode == "ai" else t("status_lost"))
        else:
            restyle(pp.status, "status")
            if self.mode == "ai":
                pp.status.setText(t("status_ai", level=ai_name.lower()))
            else:
                pp.status.setText(t("status_ready") if g.status == "ready" else t("status_play"))
        sub = self.message
        if g.no_guess_ok is False:
            sub = (t("no_guess_failed") + " " + sub).strip()
        pp.substatus.setText(sub)
        pp.substatus.setVisible(bool(sub))
        pp.hint_button.setEnabled(self.human_can_move())
        pp.hint_button.setVisible(self.mode == "human")
        pp.thoughts_hint.setVisible(show)
        info = self.thoughts_info if show else None
        if info:
            key = {"net": "thoughts_net", "novice": "thoughts_novice"}.get(
                info["source"], "thoughts_exact" if info["exact"] else "thoughts_approx")
            pp.thoughts_source.setText(t(key))
        pp.thoughts_source.setVisible(bool(info))
        pp.assisted_note.setVisible(self.mode == "human" and self.assisted and not g.over)
        pp.fit_labels()
