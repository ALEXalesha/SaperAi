"""Правила сапёра: поле, первый клик, открытие волной, флажки, аккорд, таймер.

Чистый Python без Qt. Клетки нумеруются i = y * width + x.

Что видит игрок (и ИИ - ровно это же): view() - для каждой клетки число мин рядом
(0..8), если клетка открыта; HIDDEN - закрыта; FLAG - закрыта и под флажком. После
проигрыша показываются мины (MINE), взорвавшаяся (BOOM) и неверные флажки (WRONG_FLAG).

Первый клик всегда безопасен: мины раскладываются после него. Правило first_click:
- "opening" (по умолчанию) - свободны клетка и все её соседи, первый клик открывает
  область (если мин так много, что соседям места нет, - свободна только сама клетка);
- "safe" - свободна только сама клетка (как в старом Windows).
no_guess=True - генератор перекладывает мины, пока поле не решается без угадываний
(проверка - game.ai.solver.solvable_without_guess).
"""
import random
import time

HIDDEN = -1
FLAG = -2
MINE = -3          # видна после проигрыша
BOOM = -4          # мина, на которой подорвались
WRONG_FLAG = -5    # флажок не на мине - видно после проигрыша

LEVELS = {
    # имя: (ширина, высота, мины)
    "beginner": (9, 9, 10),
    "intermediate": (16, 16, 40),
    "expert": (30, 16, 99),
}
MAX_SIDE = 60
FIRST_CLICK = ("opening", "safe")

_NEIGHBORS = {}


def neighbors(width, height):
    """Соседи каждой клетки: список кортежей. Кэшируется по размеру поля."""
    key = (width, height)
    table = _NEIGHBORS.get(key)
    if table is None:
        table = []
        for y in range(height):
            for x in range(width):
                table.append(tuple(ny * width + nx
                                   for ny in range(max(0, y - 1), min(height, y + 2))
                                   for nx in range(max(0, x - 1), min(width, x + 2))
                                   if (nx, ny) != (x, y)))
        _NEIGHBORS[key] = table
    return table


def check_size(width, height, mines):
    """ValueError, если такого поля не бывает."""
    if not (2 <= width <= MAX_SIDE and 2 <= height <= MAX_SIDE):
        raise ValueError(f"поле {width}x{height}: стороны от 2 до {MAX_SIDE}")
    if not 1 <= mines <= width * height - 1:
        raise ValueError(f"мин {mines}: от 1 до {width * height - 1}")


def safe_zone(width, height, mines, first, rule):
    """Клетки, где не может быть мины после первого клика first."""
    if rule == "opening":
        zone = {first, *neighbors(width, height)[first]}
        if width * height - len(zone) >= mines:
            return zone
    return {first}


class Game:
    """Одна партия. Ходы: reveal(i), chord(i), toggle_flag(i). Состояние: status -
    'ready' (мин ещё нет), 'playing', 'won', 'lost'."""

    def __init__(self, width, height, mines, seed=None, first_click="opening", no_guess=False,
                 clock=time.monotonic):
        check_size(width, height, mines)
        if first_click not in FIRST_CLICK:
            raise ValueError(f"first_click: {first_click!r}")
        self.width, self.height, self.mines = width, height, mines
        self.n = width * height
        self.seed = seed
        self.first_click = first_click
        self.no_guess = no_guess
        self.no_guess_ok = None          # удалось ли разложить поле без угадываний
        self.clock = clock
        self.nb = neighbors(width, height)
        self.mine = None                 # bytearray: 1 - мина
        self.count = None                # число мин рядом
        self.open = bytearray(self.n)    # 1 - открыта
        self.flag = bytearray(self.n)    # 1 - флажок
        self.opened = 0
        self.flags = 0
        self.status = "ready"
        self.exploded = -1
        self.started = None
        self.finished = None
        self.moves = 0                   # сколько раз игрок открывал клетки (клик или аккорд)

    @classmethod
    def from_layout(cls, rows, clock=time.monotonic):
        """Поле с готовыми минами для проверок: строки из '.' и '*'. Первый клик здесь не
        перекладывает мины - раскладка уже есть."""
        height, width = len(rows), len(rows[0])
        mines = sum(r.count("*") for r in rows)
        g = cls(width, height, max(mines, 1), clock=clock)
        g.mines = mines
        g._set_mines(bytearray(1 if ch == "*" else 0 for r in rows for ch in r))
        return g

    # --- раскладка ---

    def _set_mines(self, mine):
        self.mine = mine
        self.count = [sum(mine[j] for j in self.nb[i]) for i in range(self.n)]
        self.status = "playing"

    def _random_layout(self, rng, first):
        zone = safe_zone(self.width, self.height, self.mines, first, self.first_click)
        free = [i for i in range(self.n) if i not in zone]
        mine = bytearray(self.n)
        for i in rng.sample(free, self.mines):
            mine[i] = 1
        return mine

    def place_mines(self, first, attempts=3000):
        """Разложить мины после первого клика. Без угадываний - перебор раскладок, пока
        решатель не пройдёт поле от first до конца; не вышло за attempts - последняя
        раскладка, no_guess_ok=False (окно скажет)."""
        rng = random.Random(self.seed)
        if not self.no_guess:
            self._set_mines(self._random_layout(rng, first))
            return
        from game.ai.solver import solvable_without_guess
        for _ in range(attempts):
            mine = self._random_layout(rng, first)
            if solvable_without_guess(self.width, self.height, mine, first):
                self.no_guess_ok = True
                self._set_mines(mine)
                return
        self.no_guess_ok = False
        self._set_mines(mine)

    # --- ходы ---

    def reveal(self, i):
        """Открыть клетку. Возвращает список открытых клеток (пусто - ход ничего не дал)."""
        if self.status not in ("ready", "playing") or self.open[i] or self.flag[i]:
            return []
        if self.status == "ready":
            self.place_mines(i)
        if self.started is None:
            self.started = self.clock()
        self.moves += 1
        return self._open_from([i])

    def chord(self, i):
        """Аккорд: на открытой цифре, вокруг которой стоит столько же флажков, - открыть
        остальных закрытых соседей. Неверный флажок - подрыв, как у людей."""
        if self.status != "playing" or not self.open[i] or self.count[i] == 0:
            return []
        nb = self.nb[i]
        if sum(self.flag[j] for j in nb) != self.count[i]:
            return []
        targets = [j for j in nb if not self.open[j] and not self.flag[j]]
        if not targets:
            return []
        self.moves += 1
        return self._open_from(targets)

    def toggle_flag(self, i):
        """Поставить или снять флажок на закрытой клетке. True - что-то изменилось."""
        if self.status not in ("ready", "playing") or self.open[i]:
            return False
        self.flag[i] ^= 1
        self.flags += 1 if self.flag[i] else -1
        return True

    def _open_from(self, starts):
        opened = []
        for s in starts:
            if self.mine[s]:
                self.status = "lost"
                self.exploded = s
                self.finished = self.clock()
                return opened
        stack = list(starts)
        while stack:
            i = stack.pop()
            if self.open[i] or self.flag[i]:
                continue
            self.open[i] = 1
            self.opened += 1
            opened.append(i)
            if self.count[i] == 0:
                stack.extend(j for j in self.nb[i] if not self.open[j])
        if self.opened == self.n - self.mines:
            self.status = "won"
            self.finished = self.clock()
            for i in range(self.n):        # победа - все мины под флажками
                if self.mine[i] and not self.flag[i]:
                    self.flag[i] = 1
                    self.flags += 1
        return opened

    # --- что видно ---

    @property
    def over(self):
        return self.status in ("won", "lost")

    def mines_left(self):
        """Счётчик мин на табло: мины минус флажки (может уйти в минус - как в оригинале)."""
        return self.mines - self.flags

    def elapsed(self):
        """Секунды с первого клика; после конца партии - замирают."""
        if self.started is None:
            return 0.0
        end = self.finished if self.finished is not None else self.clock()
        return max(0.0, end - self.started)

    def view(self):
        """То, что видит игрок: список длины width*height."""
        out = []
        lost = self.status == "lost"
        for i in range(self.n):
            if self.open[i]:
                out.append(self.count[i])
            elif lost and i == self.exploded:
                out.append(BOOM)
            elif self.flag[i]:
                out.append(WRONG_FLAG if lost and not self.mine[i] else FLAG)
            elif lost and self.mine[i]:
                out.append(MINE)
            else:
                out.append(HIDDEN)
        return out

    def observe(self):
        """Наблюдение для ИИ: только то, что видит игрок во время партии."""
        cells = (v if v >= 0 or v == FLAG else FLAG if v == WRONG_FLAG else HIDDEN for v in self.view())
        return Observation(self.width, self.height, self.mines, cells)

    def xy(self, i):
        return i % self.width, i // self.width

    def index(self, x, y):
        return y * self.width + x


class Observation:
    """Что получает ИИ: размеры, общее число мин и видимые клетки (числа, HIDDEN, FLAG).
    Раскладки мин тут нет - ИИ не может подсмотреть."""

    __slots__ = ("width", "height", "mines", "cells")

    def __init__(self, width, height, mines, cells):
        self.width, self.height, self.mines = width, height, mines
        self.cells = tuple(cells)

    def __eq__(self, other):
        return isinstance(other, Observation) and (self.width, self.height, self.mines, self.cells) == \
            (other.width, other.height, other.mines, other.cells)

    def __hash__(self):
        return hash((self.width, self.height, self.mines, self.cells))

    def __repr__(self):
        return f"Observation({self.width}x{self.height}, {self.mines} мин)"

    @classmethod
    def parse(cls, rows, mines):
        """Для проверок: строки из цифр, '#' (закрыта) и 'F' (флажок)."""
        cells = []
        for r in rows:
            for ch in r:
                cells.append(HIDDEN if ch == "#" else FLAG if ch == "F" else int(ch))
        return cls(len(rows[0]), len(rows), mines, cells)
