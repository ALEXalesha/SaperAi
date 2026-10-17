# Мутанты правил и ИИ для tools/mutate.py: (имя, файл, было, стало, проверки).
B = "game/core/board.py"
TB = "tests/test_board.py"
MUTANTS = [
    ("rules: соседи без диагоналей", B, "if (nx, ny) != (x, y))", "if (nx, ny) != (x, y) and (nx == x or ny == y))", TB),
    ("rules: первый клик без соседей", B, "zone = {first, *neighbors(width, height)[first]}", "zone = {first}", TB),
    ("rules: первый клик не безопасен", B, "    return {first}\n\n\nclass", "    return set()\n\n\nclass", TB),
    ("rules: волна через числа", B, "if self.count[i] == 0:\n                stack", "if self.count[i] <= 1:\n                stack", TB),
    ("rules: волна сквозь флажки", B, "            if self.open[i] or self.flag[i]:\n                continue",
     "            if self.open[i]:\n                continue", TB),
    ("rules: открыть под флажком", B, "if self.status not in (\"ready\", \"playing\") or self.open[i] or self.flag[i]:",
     "if self.status not in (\"ready\", \"playing\") or self.open[i]:", TB),
    ("rules: аккорд без проверки флажков", B, "if sum(self.flag[j] for j in nb) != self.count[i]:", "if False:", TB),
    ("rules: аккорд по меньшему числу флажков", B, "if sum(self.flag[j] for j in nb) != self.count[i]:",
     "if sum(self.flag[j] for j in nb) > self.count[i]:", TB),
    ("rules: мина не взрывается", B, "            if self.mine[s]:\n                self.status = \"lost\"",
     "            if False:\n                self.status = \"lost\"", TB),
    ("rules: победа на одну клетку раньше", B, "if self.opened == self.n - self.mines:",
     "if self.opened >= self.n - self.mines - 1:", TB),
    ("rules: таймер не стоит после конца", B, "end = self.finished if self.finished is not None else (",
     "end = None if False else (", TB),
    ("rules: таймер с флажка", B, "        self.flag[i] ^= 1\n", "        self.flag[i] ^= 1\n        self.started = self.started or self.clock()\n", TB),
    ("rules: счётчик мин без флажков", B, "return self.mines - self.flags", "return self.mines", TB),
    ("rules: зерно не задаёт поле", B, "rng = random.Random(self.seed)", "rng = random.Random()", TB),
    ("rules: проигрыш не показывает мины", B, "elif lost and self.mine[i]:\n                out.append(MINE)",
     "elif False:\n                out.append(MINE)", TB),
    ("rules: неверный флажок не виден", B, "out.append(WRONG_FLAG if lost and not self.mine[i] else FLAG)",
     "out.append(FLAG)", TB),
]
S = "game/ai/solver.py"
TS = "tests/test_solver.py"
MUTANTS += [
    ("solver: флажок считается миной", S, "vs = tuple(j for j in nb[i] if cells[j] < 0)",
     "vs = tuple(j for j in nb[i] if cells[j] == -1)", TS),
    ("solver: без общего числа мин", S, "weight = {m: c * _ways(U, rem_exact - m) for m, c in total_poly.items()}",
     "weight = {m: c for m, c in total_poly.items()}", TS),
    ("solver: вес догадки без глубины", S, "w = sum(c * _ways(U, rem_exact - k - j) for j, c in others.items())",
     "w = sum(c for j, c in others.items())", TS),
    ("solver: простое правило только для мин", S, "            if need == 0 or need == len(unk):\n                val",
     "            if need == len(unk):\n                val", TS),
    ("solver: вложенность наоборот", S, "known[w] = 0 if dn == 0 else 1", "known[w] = 1 if dn == 0 else 0", TS),
    ("solver: перебор без отсечения", S, "if need[e] < 0 or need[e] > left[e]:", "if need[e] < 0:", TS),
    ("solver: глубина без мин", S, "p_in = min(1.0, max(0.0, inner_mines / (total * U)))", "p_in = 0.0", TS),
    ("solver: известные мины не вычитаются", S, "rem = obs.mines - known_mines", "rem = obs.mines", TS),
    ("solver: бюджет не пометка", S, "            exact = False\n            p = _approx_group",
     "            p = _approx_group", TS),
    ("solver: без угадываний верит догадкам", S, "        if not safe:\n            return False",
     "        if not safe:\n            return True", TS),
]
A = "game/ai/agents.py"
TA = "tests/test_agents.py"
MUTANTS += [
    ("agents: сильный не открывает безопасные", A, "        if a.safe:\n            return Move(a.safe",
     "        if False:\n            return Move(a.safe", TA),
    ("agents: догадка с наибольшим риском", A, "low = min(probs[i] for i in cand)", "low = max(probs[i] for i in cand)", TA),
    ("agents: польза наоборот", A, "best = max(scores.values())", "best = min(scores.values())", TA),
    ("agents: новичок идёт на мину", A, "cand = [i for i, v in enumerate(obs.cells) if v < 0 and known.get(i) != 1]",
     "cand = [i for i, v in enumerate(obs.cells) if v < 0]", TA),
    ("agents: первый клик всегда в середину", A, "    if obs.first_click == \"safe\":\n        return 0\n", "", TA),
]
N = "game/ai/net.py"
TN = "tests/test_net_train.py"
MUTANTS += [
    ("net: флажок как открытая", N, "    hidden = cells < 0\n", "    hidden = cells == -1\n", TN),
    ("net: без плотности мин", N, "    x[..., 10] = density[:, None, None]", "    pass", TN),
    ("net: симметрия без отражения", N, "    if k & 1:\n        a = a[:, ::-1]", "    if False:\n        a = a[:, ::-1]", TN),
    ("net: градиент наоборот", N, "        self.model.backward(g[..., None])", "        self.model.backward(-g[..., None])", TN),
    ("train: снимок без Adam", "game/train/fit.py", "        self.opt.t = int(meta[\"adam_t\"])", "        pass", TN),
    ("data: цель не от решателя", "game/train/data.py",
     "probs = np.array([p if p is not None else 0.0 for p in a.probs]",
     "probs = np.array([0.5 if p is not None else 0.0 for p in a.probs]", TN),
]
W = "game/ui/widget.py"
BV = "game/ui/board_view.py"
AT = "game/ui/ai_thread.py"
TU = "tests/test_ui.py"
MUTANTS += [
    ("ui: подсказка не помечает партию", W, "        self.assisted = True\n        self.ai.request_hint",
     "        self.ai.request_hint", TU),
    ("ui: мысли не помечают партию", W, "                self.assisted = True\n            self.probs = None",
     "                pass\n            self.probs = None", TU),
    ("ui: партия ИИ в статистику", W, "if self.mode != \"human\" or self.assisted:", "if self.assisted:", TU),
    ("ui: рекорды не пишутся", W, "            save_json(self.ctx.file(\"records.json\"), recs)", "            pass", TU),
    ("ui: пауза не останавливает", W, "if self.mode == \"ai\" and not self.paused and on_screen:",
     "if self.mode == \"ai\" and on_screen:", TU),
    ("ui: ИИ флажит догадки", W, "if q == 1.0 and not self.game.flag[i]", "if q > 0.2 and not self.game.flag[i]", TU),
    ("ui: правая кнопка открывает", BV, "            if i >= 0:\n                self.flagAt.emit(i)",
     "            if i >= 0:\n                self.revealAt.emit(i)", TU),
    ("ui: две кнопки не аккорд", BV, "if both or e.button() == Qt.MouseButton.MiddleButton:",
     "if e.button() == Qt.MouseButton.MiddleButton:", TU),
    ("ui: мысли новичка от решателя", AT, "    if level == \"novice\":", "    if False:", TU),
    ("ui: потоки не ждут", AT, "            j.wait(max(0, int((deadline - time.monotonic()) * 1000)))", "            pass", TU),
]

# графики статистики (aikit.charts)
TSC = "tests/test_stats_charts.py"
MUTANTS += [
    ("charts: партия не в журнале", W, "        self.history.record(game)", "        pass", TSC),
    ("charts: время победы и у поражения", W, "        if won:\n            game[\"win_time\"]", "        if True:\n            game[\"win_time\"]", TSC),
    ("charts: рекорд - худшее время", W, 'gamelog.best_curve(mine, "win_time", "min")', 'gamelog.best_curve(mine, "win_time", "max")', TSC),
    ("charts: время по всем полям сразу", W, '    mine = [g for g in games if g["level"] == field]', '    mine = games', TSC + " -k field_from"),
]

# стартовое меню и растянутые настройки (автор 17.10)
MN = "game/ui/menu.py"
TM = "tests/test_menu.py"
TR = "tests/test_pages.py"
MUTANTS += [
    ("menu: окно открывается полем", W, '        self.pages = {"menu": self.menu, "play": self.play,',
     '        self.pages = {"play": self.play, "menu": self.menu,', TM + " -k opens"),
    ("menu: ИИ начинает за меню", W, "            if self.mode == \"ai\" and not self.paused and on_screen:",
     "            if self.mode == \"ai\" and not self.paused:", TM + " -k behind"),
    ("menu: ИИ доигрывает за меню", W, "            self.token += 1                 # поле ушло с экрана",
     "            return                 # поле ушло с экрана", TM + " -k behind"),
    ("menu: нет «Продолжить»", W, '        return self.game is not None and self.game.status == "playing"',
     "        return False", TM + " -k continue"),
    ("menu: назад всегда на поле", W, "            self.back_page = prev           # «Назад»",
     '            self.back_page = "play"           # «Назад»', TM + " -k back"),
    ("menu: выбор уводит из меню", W, '            self.new_game(show=self.current_page() == "play")',
     "            self.new_game()", TM + " -k stays"),
    ("menu: настройки узкой колонкой", W, "        self.box = box\n", "        self.box = box\n        box.setMaximumWidth(760)\n",
     TM + " -k stretches"),
    ("menu: панель шире окна", MN, "        self.panel.setFixedWidth(round(min(470 * self.scale, max(440, self.width() * 0.46))))",
     "        self.panel.setFixedWidth(round(470 * self.scale * 1.3))", TM + " -k whole"),
    ("menu: не растёт на 4K", MN, "        return round(max(1.0, min(2.4, w / 1280, h / 800)), 2)", "        return 1.0", TM + " -k scales"),
    ("menu: волна не успевает", MN, "    wave = min(WAVE, 10.0 / max(1.0, far))", "    wave = WAVE", TM + " -k fade"),
    ("menu: цифры не по порядку", MN, "                n += 1\n                b.digit = n", "                n += 1", TM + " -k continue"),
    ("menu: боковая панель общего вида", W,
     "        self.play.side.setStyleSheet(side_qss(menu_palette(self.ctx.theme)) + lcd_qss(self.ctx.theme))",
     "        pass", TM + " -k side_panel"),
    ("menu: поле не в цветах меню", W, "        self.play.board.set_theme(self.ctx.theme, menu_palette(self.ctx.theme))",
     "        self.play.board.set_theme(self.ctx.theme)", TM + " -k side_panel"),
    ("menu: картинка не собирается заново", MN, "            self._key = None                         # время пошло назад",
     "            pass                         # время пошло назад", TM + " -k frozen"),
    # 17.10 вечер: настройки и статистика в стиле игры (aikit.skin) и находки проверки 17.10
    ("pages: клавиши партии с чужих страниц", W, '            if self.current_page() == "play":\n                slot()',
     "            slot()", TR + " -k hotkeys"),
    ("pages: часы идут в меню", W, "                self.game.pause()           # и часы стоят", "                pass", TR + " -k clock"),
    ("pages: раскладка в потоке окна", W, '        if self.needs_layout():\n            self.start_layout(i, "human")\n            return\n',
     "", TR + " -k no_guess"),
    ("pages: перебор без предела времени", B,
     "                if (cancel is not None and cancel()) or time.monotonic() - start > budget:",
     "                if cancel is not None and cancel():", TR + " -k budget"),
    ("pages: победа первым кликом в рекордах", W, "        if won and g.moves == 1:", "        if False:", TR + " -k first_click"),
    ("pages: пустая статистика молчит", W, "        self.empty_note.setVisible(not rows)", "        self.empty_note.setVisible(False)",
     TR + " -k empty"),
    ("pages: табло без окошка", W, " + lcd_qss(self.ctx.theme))", ")", TR + " -k lcd"),
    ("pages: настройки общим видом", W,
     "        super().__init__(SKIN, back=lambda: gw.go_back())\n        self.gw = gw\n        box = SettingsList()",
     "        super().__init__(None, back=lambda: gw.go_back())\n        self.gw = gw\n        box = SettingsList()",
     TR + " -k look"),
]
