"""Точный решатель: закон - вероятности совпадают с полным перебором раскладок на маленьких
полях; простые правила, вложенность, общее число мин, честная пометка приближения."""
import itertools
import random
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as hs

from game.ai import solver
from game.core.board import FLAG, HIDDEN, Game, Observation, neighbors


def brute(obs):
    """Вероятность мины в каждой закрытой клетке перебором ВСЕХ раскладок мин."""
    nb = neighbors(obs.width, obs.height)
    cells = obs.cells
    hidden = [i for i, v in enumerate(cells) if v < 0]
    nums = [(i, v) for i, v in enumerate(cells) if v >= 0]
    hits = {i: 0 for i in hidden}
    total = 0
    for combo in itertools.combinations(hidden, obs.mines):
        s = set(combo)
        if all(sum(j in s for j in nb[i]) == v for i, v in nums):
            total += 1
            for i in combo:
                hits[i] += 1
    if total == 0:
        return None
    return {i: Fraction(hits[i], total) for i in hidden}


def random_position(rng, max_hidden=13):
    """Позиция из настоящей партии на маленьком поле: несколько безопасных открытий,
    иногда флажки (верные и неверные)."""
    while True:
        w, h = rng.randint(2, 6), rng.randint(2, 5)
        m = rng.randint(1, max(1, w * h // 3))
        g = Game(w, h, m, seed=rng.randrange(10 ** 9), first_click=rng.choice(["opening", "safe"]))
        g.reveal(rng.randrange(w * h))
        for _ in range(rng.randint(0, 4)):
            if g.status != "playing":
                break
            free = [i for i in range(w * h) if not g.mine[i] and not g.open[i]]
            if free:
                g.reveal(rng.choice(free))
        if g.status != "playing":
            continue
        for _ in range(rng.randint(0, 2)):
            i = rng.randrange(w * h)
            if not g.open[i]:
                g.toggle_flag(i)
        obs = g.observe()
        if sum(v < 0 for v in obs.cells) <= max_hidden:
            return obs


@given(hs.integers(0, 10 ** 9))
def test_law_exact_probabilities_match_full_enumeration(seed):
    obs = random_position(random.Random(seed))
    want = brute(obs)
    got = solver.analyze(obs)
    assert got.exact
    for i, p in want.items():
        assert abs(got.probs[i] - float(p)) < 1e-12, (i, got.probs[i], p)
    for i, v in enumerate(obs.cells):
        if v >= 0:
            assert got.probs[i] is None
    assert set(got.safe) == {i for i, p in want.items() if p == 0}
    assert set(got.mines) == {i for i, p in want.items() if p == 1}


@given(hs.integers(0, 10 ** 9))
def test_law_without_subset_rule_same_answer(seed):
    obs = random_position(random.Random(seed))
    a = solver.analyze(obs, subset=True)
    b = solver.analyze(obs, subset=False)
    assert all((x is None and y is None) or abs(x - y) < 1e-12 for x, y in zip(a.probs, b.probs))


@given(hs.integers(0, 10 ** 9))
def test_probabilities_sum_to_mine_count(seed):
    obs = random_position(random.Random(seed), max_hidden=40)
    a = solver.analyze(obs)
    assert abs(sum(p for p in a.probs if p is not None) - obs.mines) < 1e-9


def test_flags_are_not_trusted():
    # флажок стоит на клетке, где мины быть не может: решатель его не слушает
    obs = Observation.parse(["F1#",
                             "011",
                             "000"], 1)
    a = solver.analyze(obs)
    assert a.probs[0] == 0.0 and a.probs[2] == 1.0


def test_simple_rules_one_two_one():
    # классика 1-2-1 у стены: мины напротив единиц, напротив двойки свободно
    obs = Observation.parse(["###",
                             "121",
                             "000"], 2)
    known = solver.propagate(solver.equations(obs), subset=True)
    assert known == {0: 1, 1: 0, 2: 1}


def test_subset_rule_needed():
    # «1» внутри «1»: без правила вложенности одно простое правило ничего не знает
    obs = Observation.parse(["####",
                             "#11#",
                             "####"], 2)
    assert solver.propagate(solver.equations(obs), subset=False) == {}
    # левая единица видит {0, 1}, правая - {0, 1, 2} (5 и 8 свободны по нулю):
    # клетка 2 свободна только по вложенности
    obs2 = Observation.parse(["###",
                              "11#",
                              "00#"], 1)
    assert solver.propagate(solver.equations(obs2), subset=False) == {5: 0, 8: 0}
    known = solver.propagate(solver.equations(obs2), subset=True)
    assert known == {2: 0, 5: 0, 8: 0}


def test_simple_known_is_single_rule_only():
    obs = Observation.parse(["###",
                             "11#",
                             "00#"], 1)
    assert solver.simple_known(obs) == {5: 0, 8: 0}


def test_global_mine_count_decides():
    # у единицы три закрытых соседа и ровно одна мина; остальные мины - в глубине из 5 клеток
    for mines, p_in in ((2, 1 / 5), (5, 4 / 5)):
        obs = Observation.parse(["1##",
                                 "###",
                                 "###"], mines)
        a = solver.analyze(obs)
        assert a.probs[1] == pytest.approx(1 / 3) and a.probs[4] == pytest.approx(1 / 3)
        assert a.probs[8] == pytest.approx(p_in)
        want = brute(obs)
        assert all(abs(a.probs[i] - float(q)) < 1e-12 for i, q in want.items())


def test_start_of_game_uniform():
    obs = Observation(9, 9, 10, [HIDDEN] * 81)
    a = solver.analyze(obs)
    assert all(p == pytest.approx(10 / 81) for p in a.probs)


def test_inconsistent_numbers_raise():
    with pytest.raises(solver.Inconsistent):
        solver.analyze(Observation.parse(["3#", "00"], 1))
    with pytest.raises(solver.Inconsistent):
        solver.analyze(Observation.parse(["1#", "#1"], 3))   # мин больше, чем помещается
    with pytest.raises(solver.Inconsistent):
        solver.analyze(Observation.parse(["21", "##"], 1))   # 2 и 1 против одной мины


def test_budget_exceeded_marked_approximate():
    g = Game(30, 16, 99, seed=11)
    g.reveal(240)
    obs = g.observe()
    a = solver.analyze(obs, budget=5)
    assert solver.analyze(obs).exact and not a.exact
    assert all(0.0 <= a.probs[i] <= 1.0 for i, v in enumerate(obs.cells) if v < 0)


def test_sure_moves_are_really_safe():
    rng = random.Random(7)
    for _ in range(30):
        g = Game(16, 16, 40, seed=rng.randrange(10 ** 9))
        g.reveal(rng.randrange(256))
        while g.status == "playing":
            safe, mines = solver.sure_moves(g.observe())
            assert all(not g.mine[i] for i in safe)
            assert all(g.mine[i] for i in mines)
            if not safe:
                break
            for i in safe:
                g.reveal(i)


def test_solvable_without_guess_simple():
    mine = bytearray(16)
    mine[15] = 1                      # мина в углу: волна от 0 открывает всё остальное
    assert solver.solvable_without_guess(4, 4, mine, 0)
    m2 = bytearray(4)
    m2[3] = 1                         # 2x2, одна мина, клик в 0: все три соседа - «1», чистое угадывание
    assert not solver.solvable_without_guess(2, 2, m2, 0)


@given(hs.integers(0, 10 ** 9))
def test_law_solvable_without_guess_matches_brute(seed):
    rng = random.Random(seed)
    w, h = rng.randint(3, 4), rng.randint(3, 4)
    m = rng.randint(1, 4)
    g = Game(w, h, m, seed=seed, first_click="safe")
    first = rng.randrange(w * h)
    g.reveal(first)
    if g.status == "lost":
        return
    mine = bytes(g.mine)
    g2 = Game(w, h, m)
    g2._set_mines(bytearray(mine))
    g2.reveal(first)
    assert solver.solvable_without_guess(w, h, mine, first) == (not brute_guess_needed(g2))


def brute_guess_needed(g):
    while g.status == "playing":
        p = brute(g.observe())
        safe = [i for i, q in p.items() if q == 0]
        if not safe:
            return True
        for i in safe:
            g.reveal(i)
    return False


def test_no_guess_board_is_solved_by_solver():
    for seed in range(5):
        g = Game(9, 9, 10, seed=seed, no_guess=True)
        g.reveal(40)
        assert g.no_guess_ok
        while g.status == "playing":
            safe, _ = solver.sure_moves(g.observe())
            assert safe, "на поле без угадываний решатель застрял"
            for i in safe:
                g.reveal(i)
        assert g.status == "won"


def test_flag_value_kept_out():
    obs = Observation.parse(["F#", "##"], 1)
    a = solver.analyze(obs)
    assert all(p == pytest.approx(0.25) for p in a.probs)
    assert FLAG in obs.cells
