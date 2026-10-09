"""Точный решатель сапёра: вероятность мины в каждой закрытой клетке.

Работает только с наблюдением (Observation): открытые числа, закрытые клетки и общее
число мин. Флажки решатель не считает минами - флажок ставит человек и может ошибиться;
для решателя клетка под флажком просто закрыта.

Как считается:
1. Каждое открытое число даёт уравнение: сумма мин среди его закрытых соседей = числу.
   Закрытые клетки рядом с числами - «граница», остальные закрытые - «глубина».
2. Простые правила до неподвижной точки: число уже набрано - остальные соседи свободны;
   закрытых соседей ровно столько, сколько не хватает, - все мины. Затем правило
   вложенности: уравнение A внутри уравнения B - разность B без A получает свою сумму.
3. Оставшиеся клетки границы делятся на независимые группы (связаны общими уравнениями).
   В каждой группе перебираются ВСЕ раскладки, согласные с числами: для каждого числа мин k
   в группе - сколько раскладок N[k] и сколько из них с миной в каждой клетке S[k][v].
4. Группы сводятся вместе с общим числом мин: раскладка границы с m минами весит
   C(глубина, осталось - m) - столько способов разложить остальные мины в глубину. Счёт -
   целыми числами Python, без округлений; деление - только в конце.

Для больших групп перебор ограничен бюджетом узлов. Не уложились - вероятности этой
группы приближаются согласованием по уравнениям (как в учёте карт DurakAi), и в ответе
exact=False: окно это честно показывает.
"""
from math import comb

from game.core.board import neighbors

BUDGET = 300_000


class Inconsistent(ValueError):
    """Числа на поле противоречат друг другу или общему числу мин."""


class Analysis:
    """probs - вероятность мины по клеткам (None у открытых); safe и mines - клетки с
    вероятностью ровно 0 и ровно 1; exact - всё посчитано точным перебором."""

    __slots__ = ("probs", "safe", "mines", "exact", "frontier", "nodes", "groups")

    def __init__(self, probs, safe, mines, exact, frontier, nodes, groups):
        self.probs = probs
        self.safe = safe
        self.mines = mines
        self.exact = exact
        self.frontier = frontier
        self.nodes = nodes
        self.groups = groups

    def hidden(self):
        return [i for i, p in enumerate(self.probs) if p is not None]


def equations(obs):
    """[(закрытые соседи, число)] по открытым клеткам. Число без закрытых соседей обязано
    быть нулём - иначе Inconsistent."""
    cells = obs.cells
    nb = neighbors(obs.width, obs.height)
    out = []
    for i, v in enumerate(cells):
        if v < 0:
            continue
        vs = tuple(j for j in nb[i] if cells[j] < 0)
        if vs:
            out.append((vs, v))       # число больше закрытых соседей поймает _reduce
        elif v != 0:
            raise Inconsistent(f"клетка {i}: {v} мин без закрытых соседей")
    return out


def _reduce(eqs, known):
    """Уравнение без известных клеток: (frozenset неизвестных, сколько мин среди них)."""
    out = []
    for vs, c in eqs:
        unk = []
        need = c
        for v in vs:
            k = known.get(v)
            if k is None:
                unk.append(v)
            else:
                need -= k
        if need < 0 or need > len(unk):
            raise Inconsistent("числа противоречат друг другу")
        if unk:
            out.append((frozenset(unk), need))
    return out


def propagate(eqs, known=None, subset=True):
    """Простые правила (и правило вложенности, если subset) до неподвижной точки.
    Возвращает {клетка: 0 или 1} - всё, что известно наверняка."""
    known = dict(known or {})
    while True:
        changed = False
        red = _reduce(eqs, known)
        for unk, need in red:
            if need == 0 or need == len(unk):
                val = 0 if need == 0 else 1
                for v in unk:
                    if v not in known:
                        known[v] = val
                        changed = True
        if changed:
            continue
        if not subset:
            return known
        # правило вложенности: только пары уравнений с общей клеткой
        uniq = list({(u, n) for u, n in red})
        by_var = {}
        for k, (u, _) in enumerate(uniq):
            for v in u:
                by_var.setdefault(v, []).append(k)
        for a, (ua, na) in enumerate(uniq):
            seen = set()
            for v in ua:
                for b in by_var[v]:
                    if b == a or b in seen:
                        continue
                    seen.add(b)
                    ub, nb_ = uniq[b]
                    if len(ua) < len(ub) and ua <= ub:
                        diff = ub - ua
                        dn = nb_ - na
                        if dn < 0 or dn > len(diff):
                            raise Inconsistent("числа противоречат друг другу")
                        if dn == 0 or dn == len(diff):
                            for w in diff:
                                if w not in known:
                                    known[w] = 0 if dn == 0 else 1
                                    changed = True
        if not changed:
            return known


def simple_known(obs):
    """Только самое простое правило (одно число за раз) - так играет новичок."""
    return propagate(equations(obs), subset=False)


def _groups(red):
    """Независимые группы клеток границы: (клетки, уравнения группы)."""
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for unk, _ in red:
        for v in unk:
            parent.setdefault(v, v)
        first = next(iter(unk))
        for v in unk:
            ra, rb = find(first), find(v)
            if ra != rb:
                parent[rb] = ra
    groups = {}
    for unk, need in red:
        groups.setdefault(find(next(iter(unk))), []).append((unk, need))
    out = []
    for eqs in groups.values():
        cells = set()
        for unk, _ in eqs:
            cells |= unk
        out.append((cells, eqs))
    return out


class TooBig(Exception):
    pass


def enumerate_group(cells, eqs, budget):
    """Полный перебор раскладок группы. Возвращает (order, N, S, узлы): N[k] - число
    раскладок с k минами, S[k][p] - из них с миной в клетке order[p]."""
    # порядок обхода - в ширину по уравнениям: уравнение закрывается скоро после начала,
    # и тупиковые ветки отсекаются рано
    eq_of = {v: [] for v in cells}
    for e, (unk, _) in enumerate(eqs):
        for v in unk:
            eq_of[v].append(e)
    start = min(cells, key=lambda v: (len(eq_of[v]), v))
    order, seen, queue = [], {start}, [start]
    while queue:
        v = queue.pop(0)
        order.append(v)
        for e in eq_of[v]:
            for w in sorted(eqs[e][0]):
                if w not in seen:
                    seen.add(w)
                    queue.append(w)
    n = len(order)
    eqs_at = [eq_of[v] for v in order]
    need = [nd for _, nd in eqs]
    left = [len(u) for u, _ in eqs]
    N = {}
    S = {}
    stack = []           # позиции с миной
    nodes = 0

    def go(p):
        nonlocal nodes
        nodes += 1
        if nodes > budget:
            raise TooBig
        if p == n:
            k = len(stack)
            N[k] = N.get(k, 0) + 1
            row = S.get(k)
            if row is None:
                row = S[k] = [0] * n
            for q in stack:
                row[q] += 1
            return
        es = eqs_at[p]
        for val in (0, 1):
            ok = True
            for e in es:
                left[e] -= 1
                need[e] -= val
                if need[e] < 0 or need[e] > left[e]:
                    ok = False
            if ok:
                if val:
                    stack.append(p)
                go(p + 1)
                if val:
                    stack.pop()
            for e in es:
                left[e] += 1
                need[e] += val

    go(0)
    return order, N, S, nodes


def _approx_group(cells, eqs, density, rounds=60):
    """Приближение для группы, которую не перебрать: вероятности подгоняются так, чтобы
    в каждом уравнении сумма вероятностей равнялась числу (по очереди, как Синкхорн)."""
    p = {v: density for v in cells}
    for _ in range(rounds):
        acc = {v: [] for v in cells}
        for unk, need in eqs:
            s = sum(p[v] for v in unk)
            for v in unk:
                if s > 0:
                    acc[v].append(min(1.0, p[v] * need / s))
                else:
                    acc[v].append(need / len(unk))
        p = {v: min(0.999, max(0.001, sum(a) / len(a))) for v, a in acc.items()}
    return p


def _conv(a, b):
    out = {}
    for i, x in a.items():
        for j, y in b.items():
            out[i + j] = out.get(i + j, 0) + x * y
    return out


def _ways(u, r):
    return comb(u, r) if 0 <= r <= u else 0


def analyze(obs, budget=BUDGET, subset=True):
    """Вероятность мины в каждой клетке по наблюдению. Inconsistent - если чисел и общего
    числа мин не согласовать ни одной раскладкой."""
    cells = obs.cells
    n = len(cells)
    hidden = [i for i in range(n) if cells[i] < 0]
    eqs = equations(obs)
    frontier = set()
    for vs, _ in eqs:
        frontier.update(vs)
    known = propagate(eqs, subset=subset)
    red = _reduce(eqs, known)
    known_mines = sum(known.values())
    rem = obs.mines - known_mines
    inner = [i for i in hidden if i not in frontier]
    U = len(inner)
    groups = _groups(red)
    exact = True
    nodes = 0
    dists = []            # (order, N, S) точных групп
    approx = {}           # клетка -> вероятность у неперебранных групп
    approx_mines = 0.0
    density = max(0.0, min(1.0, rem / max(1, len(hidden) - len(known))))
    for gcells, geqs in groups:
        try:
            order, N, S, k = enumerate_group(gcells, geqs, budget - nodes)
            nodes += k
            if not N:
                raise Inconsistent("у группы нет ни одной раскладки")
            dists.append((order, N, S))
        except TooBig:
            nodes = budget
            exact = False
            p = _approx_group(gcells, geqs, density)
            approx.update(p)
            approx_mines += sum(p.values())
    rem_exact = rem - round(approx_mines)

    probs = [None] * n
    for v, val in known.items():
        probs[v] = float(val)
    # произведение распределений всех групп и «все, кроме одной»
    total_poly = {0: 1}
    for _, N, _ in dists:
        total_poly = _conv(total_poly, N)
    weight = {m: c * _ways(U, rem_exact - m) for m, c in total_poly.items()}
    total = sum(weight.values())
    if total == 0:
        if exact:
            raise Inconsistent("общее число мин не сходится с числами на поле")
        total = 1
    for gi, (order, N, S) in enumerate(dists):
        others = {0: 1}
        for gj, (_, N2, _) in enumerate(dists):
            if gj != gi:
                others = _conv(others, N2)
        acc = [0] * len(order)
        for k, row in S.items():
            w = sum(c * _ways(U, rem_exact - k - j) for j, c in others.items())
            if w:
                for q, s in enumerate(row):
                    acc[q] += s * w
        for q, v in enumerate(order):
            probs[v] = acc[q] / total
    for v, p in approx.items():
        probs[v] = p
    if U:
        inner_mines = sum(c * (rem_exact - m) for m, c in weight.items())
        p_in = min(1.0, max(0.0, inner_mines / (total * U)))
        for i in inner:
            probs[i] = p_in
    safe = sorted(i for i in hidden if probs[i] == 0.0)
    mines = sorted(i for i in hidden if probs[i] == 1.0)
    return Analysis(probs, safe, mines, exact, frontier, nodes, len(groups))


def sure_moves(obs, budget=BUDGET):
    """Клетки, открыть которые точно безопасно, и точные мины: сначала дешёвые правила,
    перебор - только если они ничего не дали."""
    eqs = equations(obs)
    known = propagate(eqs, subset=True)
    safe = [v for v, k in known.items() if k == 0]
    if safe:
        return sorted(safe), sorted(v for v, k in known.items() if k == 1)
    a = analyze(obs, budget=budget)
    if not a.exact:
        return [], a.mines
    return a.safe, a.mines


def solvable_without_guess(width, height, mine, first, budget=BUDGET):
    """Проходится ли поле от первого клика first одними безопасными ходами."""
    from game.core.board import Game
    g = Game(width, height, max(1, sum(mine)))
    g.mines = sum(mine)
    g._set_mines(bytearray(mine))
    g.reveal(first)
    while g.status == "playing":
        safe, _ = sure_moves(g.observe(), budget)
        if not safe:
            return False
        for i in safe:
            g.reveal(i)
    return g.status == "won"
