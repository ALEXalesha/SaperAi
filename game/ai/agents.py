"""Игроки-ИИ. Каждый получает только Observation (что видит человек) и зерно.

Ход - Move: какие клетки открыть (несколько сразу, если все точно безопасны) и была ли
это догадка. Уровни (spec, п. 2):
- новичок - только простое правило (одно число за раз), иначе случайная клетка;
- средний - сеть: открывает разом все клетки, где сеть почти уверена (риск < NET_SURE),
  иначе клетку, где сеть видит меньше всего риска;
- сильный - точный решатель: безопасные клетки, а без них - клетка с наименьшей
  вероятностью мины; при равенстве - где больше пользы (см. guess_score).
"""
import random

from game.ai import solver
from game.core.board import neighbors

LEVELS = ("novice", "medium", "strong")
TIE = 1e-9
NET_SURE = 0.005      # клетки, где сеть видит риск меньше 0,5 %, средний открывает разом


class Move:
    __slots__ = ("cells", "guess", "risk", "probs", "exact")

    def __init__(self, cells, guess, risk, probs=None, exact=True):
        self.cells = list(cells)
        self.guess = guess          # True - ни одной точно безопасной клетки не было
        self.risk = risk            # вероятность мины в открываемой клетке (у догадки)
        self.probs = probs          # вероятности по клеткам, если ИИ их считал
        self.exact = exact

    def __repr__(self):
        return f"Move({self.cells}, guess={self.guess}, risk={self.risk:.3f})"


def first_cell(obs):
    """Первый клик. С правилом «opening» - середина: вокруг первого клика гарантированно
    пусто, и в середине открывается область больше, чем у стены. С правилом «safe» - угол:
    у угла три соседа, и ноль (а с ним область) выпадает чаще всего. Замер на профи по 2000
    партий: opening - середина 48,9 %, угол 46,4 %; safe - середина 33,0 %, угол 38,1 %."""
    if obs.first_click == "safe":
        return 0
    return (obs.height // 2) * obs.width + obs.width // 2


def untouched(obs):
    return all(v < 0 for v in obs.cells)


def guess_score(obs, probs, i):
    """Польза догадки: насколько вероятно, что клетка и её закрытые соседи свободны, -
    тогда откроется ноль или число, которое многое скажет. У угла и края соседей меньше,
    поэтому при равном риске выбирается клетка ближе к углу."""
    s = 1.0 - probs[i]
    for j in neighbors(obs.width, obs.height)[i]:
        if obs.cells[j] < 0:
            s *= 1.0 - probs[j]
    return s


def pick_guess(obs, probs, rng=None):
    """Клетка с наименьшим риском, при равенстве - с наибольшей пользой, затем случайно."""
    cand = [i for i, p in enumerate(probs) if p is not None and p < 1.0]
    low = min(probs[i] for i in cand)
    ties = [i for i in cand if probs[i] <= low + TIE]
    if len(ties) > 1:
        scores = {i: guess_score(obs, probs, i) for i in ties}
        best = max(scores.values())
        ties = [i for i in ties if scores[i] >= best - TIE]
    return (rng or random).choice(ties) if len(ties) > 1 else ties[0]


class NoviceAgent:
    level = "novice"

    def choose(self, obs, rng):
        if untouched(obs):
            return Move([rng.randrange(len(obs.cells))], True, 0.0)
        known = solver.simple_known(obs)
        safe = sorted(v for v, k in known.items() if k == 0)
        if safe:
            return Move(safe, False, 0.0)
        cand = [i for i, v in enumerate(obs.cells) if v < 0 and known.get(i) != 1]
        return Move([rng.choice(cand)], True, float("nan"))


class StrongAgent:
    level = "strong"

    def __init__(self, budget=solver.BUDGET):
        self.budget = budget

    def choose(self, obs, rng):
        if untouched(obs):
            return Move([first_cell(obs)], True, obs.mines / len(obs.cells))
        a = solver.analyze(obs, budget=self.budget)
        if a.safe:
            return Move(a.safe, False, 0.0, a.probs, a.exact)
        i = pick_guess(obs, a.probs, rng)
        return Move([i], True, a.probs[i], a.probs, a.exact)


class NetAgent:
    level = "medium"

    def __init__(self, net):
        self.net = net

    def choose(self, obs, rng):
        if untouched(obs):
            return Move([first_cell(obs)], True, obs.mines / len(obs.cells))
        probs = self.net.probabilities(obs)
        sure = [i for i, p in enumerate(probs) if p is not None and p < NET_SURE]
        if sure:
            return Move(sure, False, max(probs[i] for i in sure), probs, False)
        i = pick_guess(obs, probs, rng)
        return Move([i], True, probs[i], probs, False)


def make_agent(level, net=None):
    if level == "novice":
        return NoviceAgent()
    if level == "strong":
        return StrongAgent()
    if level == "medium":
        if net is None:
            from game.ai.net import default_net
            net = default_net()
        if net is None:
            raise RuntimeError("сеть не обучена")
        return NetAgent(net)
    raise ValueError(level)
