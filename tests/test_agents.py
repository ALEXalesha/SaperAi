"""ИИ-игроки: сильный открывает все безопасные клетки, догадка - наименьший риск и польза,
новичок не идёт на известную мину, честность - решение зависит только от видимого."""
import itertools
import random

from hypothesis import given
from hypothesis import strategies as hs

from game.ai import solver
from game.ai.agents import NoviceAgent, StrongAgent, first_cell, guess_score, pick_guess
from game.ai.tournament import play, run
from game.core.board import HIDDEN, Game, Observation, neighbors


def mid_game(seed, w=16, h=16, m=40, steps=None):
    """Позиция из середины партии сильного ИИ (сама партия ещё идёт)."""
    rng = random.Random(seed)
    g = Game(w, h, m, seed=seed)
    agent = StrongAgent()
    steps = rng.randint(1, 8) if steps is None else steps
    for _ in range(steps):
        if g.over:
            break
        mv = agent.choose(g.observe(), rng)
        for i in mv.cells:
            g.reveal(i)
            if g.over:
                break
    return g


def test_strong_opens_every_safe_cell_at_once():
    obs = Observation.parse(["###",
                             "121",
                             "000"], 2)
    mv = StrongAgent().choose(obs, random.Random(0))
    assert mv.cells == [1] and not mv.guess and mv.risk == 0.0


def test_first_move_is_centre():
    obs = Observation(30, 16, 99, [HIDDEN] * 480)
    mv = StrongAgent().choose(obs, random.Random(0))
    assert mv.cells == [first_cell(obs)] == [8 * 30 + 15]
    safe = Observation(30, 16, 99, [HIDDEN] * 480, first_click="safe")
    assert StrongAgent().choose(safe, random.Random(0)).cells == [0]


def test_guess_takes_lowest_risk():
    probs = [None, 0.5, 0.2, 0.3, None]
    obs = Observation(5, 1, 1, [1, HIDDEN, HIDDEN, HIDDEN, 1])
    assert pick_guess(obs, probs) == 2


def test_guess_tie_prefers_corner():
    # одинаковый риск везде: угол (меньше соседей) полезнее середины
    obs = Observation(5, 5, 5, [HIDDEN] * 25)
    probs = [0.2] * 25
    assert {pick_guess(obs, probs, random.Random(r)) for r in range(30)} == {0, 4, 20, 24}
    assert guess_score(obs, probs, 0) > guess_score(obs, probs, 12)


@given(hs.integers(0, 10 ** 6))
def test_strong_move_is_safe_or_min_risk(seed):
    g = mid_game(seed)
    if g.over:
        return
    obs = g.observe()
    mv = StrongAgent().choose(obs, random.Random(seed))
    a = solver.analyze(obs)
    if a.safe:
        assert mv.cells == a.safe and all(not g.mine[i] for i in mv.cells)
    else:
        low = min(p for p in a.probs if p is not None)
        assert abs(a.probs[mv.cells[0]] - low) < 1e-9


def test_novice_never_steps_on_known_mine():
    agent = NoviceAgent()
    checked = 0
    for seed in range(3000):
        if checked >= 15:
            break
        g = mid_game(seed, steps=2 + seed % 4)
        if g.over:
            continue
        obs = g.observe()
        known = solver.simple_known(obs)
        mines = {v for v, k in known.items() if k == 1}
        if not mines or any(k == 0 for k in known.values()):
            continue
        for r in range(20):
            mv = agent.choose(obs, random.Random(r))
            assert mv.guess and not set(mv.cells) & mines
        checked += 1
    assert checked >= 15


def test_novice_opens_simple_safe_cells():
    obs = Observation.parse(["###",
                             "11#",
                             "00#"], 1)
    mv = NoviceAgent().choose(obs, random.Random(0))
    assert mv.cells == [5, 8] and not mv.guess


@given(hs.integers(0, 10 ** 9))
def test_law_honesty_same_view_same_decision(seed):
    """Две разные раскладки мин с одинаковым видимым полем - одинаковое решение."""
    rng = random.Random(seed)
    w, h, m = 5, 4, rng.randint(2, 5)
    g = Game(w, h, m, seed=seed)
    g.reveal(rng.randrange(w * h))
    if g.status != "playing":
        return
    obs = g.observe()
    nb = neighbors(w, h)
    hidden = [i for i, v in enumerate(obs.cells) if v < 0]
    nums = [(i, v) for i, v in enumerate(obs.cells) if v >= 0]
    others = []
    for combo in itertools.combinations(hidden, m):
        s = set(combo)
        if all(sum(j in s for j in nb[i]) == v for i, v in nums) and s != {i for i in range(w * h) if g.mine[i]}:
            others.append(combo)
            if len(others) >= 3:
                break
    for combo in others:
        g2 = Game(w, h, m)
        g2._set_mines(bytearray(1 if i in combo else 0 for i in range(w * h)))
        for i in range(w * h):
            if g.open[i]:
                g2.open[i] = 1
                g2.opened += 1
        assert g2.observe() == obs
        for agent in (StrongAgent(), NoviceAgent()):
            a = agent.choose(obs, random.Random(seed))
            b = agent.choose(g2.observe(), random.Random(seed))
            assert a.cells == b.cells


def test_tournament_game_reproducible():
    a = run("strong", "beginner", 1, seed=5, indices=[7])
    b = run("strong", "beginner", 1, seed=5, indices=[7])
    assert a["results"] == b["results"]
    r1 = play(StrongAgent(), 9, 9, 10, seed=123)
    r2 = play(StrongAgent(), 9, 9, 10, seed=123)
    assert [r1[k] for k in ("won", "guesses", "steps")] == [r2[k] for k in ("won", "guesses", "steps")]
    assert r1["steps"] >= 1


def test_strong_beats_novice_on_small_sample():
    s = run("strong", "intermediate", 60, seed=9)
    n = run("novice", "intermediate", 60, seed=9)
    assert s["wins"] > n["wins"]
