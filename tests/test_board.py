"""Правила сапёра: ручные поля на каждое правило и случайные партии с инвариантами."""
import random

import pytest
from hypothesis import given
from hypothesis import strategies as hs

from game.core.board import (BOOM, FLAG, HIDDEN, LEVELS, MINE, WRONG_FLAG, Game, Observation, check_size,
                             neighbors, safe_zone)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_levels_are_classic():
    assert LEVELS == {"beginner": (9, 9, 10), "intermediate": (16, 16, 40), "expert": (30, 16, 99)}


def test_neighbors_corner_edge_middle():
    nb = neighbors(4, 3)
    assert sorted(nb[0]) == [1, 4, 5]
    assert sorted(nb[1]) == [0, 2, 4, 5, 6]
    assert sorted(nb[5]) == [0, 1, 2, 4, 6, 8, 9, 10]
    assert all(len(set(x)) == len(x) for x in nb)
    for i, x in enumerate(nb):              # соседство взаимно
        assert all(i in nb[j] for j in x)


@pytest.mark.parametrize("w,h,m", [(1, 5, 1), (5, 61, 3), (3, 3, 0), (3, 3, 9)])
def test_bad_sizes_rejected(w, h, m):
    with pytest.raises(ValueError):
        check_size(w, h, m)


def test_numbers_count_neighbour_mines():
    g = Game.from_layout(["*..",
                          "...",
                          "..*"])
    assert g.count == [0, 1, 0,
                       1, 2, 1,
                       0, 1, 0]


def test_flood_opens_zero_area_and_its_border_only():
    g = Game.from_layout(["....",
                          "....",
                          "...*",
                          "...."])
    opened = g.reveal(0)
    # угол 15 - единица, к ней не ведёт ни один ноль: волна до неё не доходит
    assert len(opened) == 14 and g.view()[15] == HIDDEN and g.status == "playing"
    g = Game.from_layout(["....",
                          "....",
                          "****",
                          "...."])
    g.reveal(0)
    v = g.view()
    # верхняя строка - нули, вторая - каёмка из чисел, за стеной мин ничего не открылось
    assert v[:4] == [0, 0, 0, 0] and v[4:8] == [2, 3, 3, 2]
    assert v[12:] == [HIDDEN] * 4 and g.opened == 8


def test_flood_skips_flagged_cells():
    g = Game.from_layout(["....",
                          "....",
                          "...*"])
    g.toggle_flag(1)
    g.reveal(8)
    assert g.view()[1] == FLAG and not g.open[1]
    assert g.open[0] and g.open[2]          # волна обошла флажок


def test_click_on_number_opens_only_it():
    g = Game.from_layout(["*..",
                          "...",
                          "..."])
    assert g.reveal(1) == [1]
    assert g.view()[1] == 1 and g.opened == 1


def test_mine_click_loses_and_shows_board():
    g = Game.from_layout(["*.",
                          ".."])
    g.toggle_flag(3)                         # неверный флажок
    g.reveal(0)
    assert g.status == "lost" and g.exploded == 0
    v = g.view()
    assert v[0] == BOOM and v[3] == WRONG_FLAG
    assert g.reveal(1) == [] and not g.toggle_flag(1)


def test_lost_shows_other_mines():
    g = Game.from_layout(["*.*",
                          "...",
                          "..."])
    g.reveal(2)
    assert g.view()[0] == MINE


def test_flags_block_reveal_and_count_down():
    g = Game.from_layout(["*..",
                          "...",
                          "..."])
    assert g.toggle_flag(0) and g.view()[0] == FLAG and g.mines_left() == 0
    assert g.reveal(0) == []
    assert g.toggle_flag(0) and g.mines_left() == 1
    g.reveal(8)
    assert not g.toggle_flag(8)              # на открытой - нельзя


def test_flag_counter_can_go_negative():
    g = Game.from_layout(["*..", "...", "..."])
    for i in (3, 4, 5):
        g.toggle_flag(i)
    assert g.mines_left() == -2


def test_win_flags_all_mines():
    g = Game.from_layout(["*.",
                          ".."])
    for i in (1, 2, 3):
        g.reveal(i)
    assert g.status == "won" and g.view()[0] == FLAG and g.mines_left() == 0


def test_chord_opens_neighbours_when_flags_match():
    g = Game.from_layout(["*..",
                          "...",
                          "..."])
    g.reveal(4)
    assert g.chord(4) == []                  # флажков нет - ничего
    g.toggle_flag(0)
    opened = g.chord(4)
    assert set(opened) >= {1, 3}
    assert g.status == "won"


def test_chord_with_wrong_flag_explodes():
    g = Game.from_layout(["*..",
                          "...",
                          "..."])
    g.reveal(4)
    g.toggle_flag(1)
    g.chord(4)
    assert g.status == "lost" and g.exploded == 0


def test_chord_needs_exact_flag_count():
    g = Game.from_layout(["*..",
                          "...",
                          "..."])
    g.reveal(4)
    g.toggle_flag(0)
    g.toggle_flag(1)
    assert g.chord(4) == [] and g.status == "playing"


def test_chord_on_zero_or_hidden_does_nothing():
    g = Game.from_layout(["*...",
                          "....",
                          "....",
                          "...."])
    g.reveal(15)
    assert g.view()[15] == 0
    assert g.chord(15) == [] and g.chord(0) == []


def test_timer_starts_on_first_reveal_and_stops_at_end():
    c = Clock()
    g = Game(9, 9, 10, seed=1, clock=c)
    g.toggle_flag(40)
    c.t += 5
    assert g.elapsed() == 0.0                # флажок таймер не запускает
    g.toggle_flag(40)
    g.reveal(40)
    c.t += 7
    assert g.elapsed() == 7.0
    mine = g.mine.index(1)
    g.reveal(mine)
    c.t += 30
    assert g.status == "lost" and g.elapsed() == 7.0


@given(hs.integers(0, 10 ** 6), hs.sampled_from(sorted(LEVELS)), hs.data())
def test_first_click_always_safe_and_opens_area(seed, level, data):
    w, h, m = LEVELS[level]
    first = data.draw(hs.integers(0, w * h - 1))
    rule = data.draw(hs.sampled_from(["opening", "safe"]))
    g = Game(w, h, m, seed=seed, first_click=rule)
    g.reveal(first)
    assert g.status in ("playing", "won")
    assert sum(g.mine) == m
    for i in safe_zone(w, h, m, first, rule):
        assert not g.mine[i]
    if rule == "opening":
        assert g.count[first] == 0 and g.opened >= len(neighbors(w, h)[first]) + 1


def test_opening_falls_back_to_cell_when_board_is_crowded():
    g = Game(3, 3, 7, seed=5, first_click="opening")
    g.reveal(4)
    assert not g.mine[4] and sum(g.mine) == 7


def test_same_seed_same_board():
    a, b = Game(16, 16, 40, seed=42), Game(16, 16, 40, seed=42)
    a.reveal(100)
    b.reveal(100)
    assert a.mine == b.mine
    c = Game(16, 16, 40, seed=43)
    c.reveal(100)
    assert c.mine != a.mine


def test_observation_has_no_mines():
    g = Game(9, 9, 10, seed=3)
    g.reveal(40)
    obs = g.observe()
    assert not hasattr(obs, "mine")
    assert all(v >= 0 or v in (HIDDEN, FLAG) for v in obs.cells)
    assert obs.mines == 10 and len(obs.cells) == 81


def test_observation_parse():
    o = Observation.parse(["1#", "F2"], 2)
    assert o.cells == (1, HIDDEN, FLAG, 2) and o.width == 2 and o.height == 2


@given(hs.integers(0, 10 ** 6))
def test_random_play_invariants(seed):
    rng = random.Random(seed)
    w, h = rng.randint(2, 12), rng.randint(2, 12)
    m = rng.randint(1, w * h - 1)
    g = Game(w, h, m, seed=seed, first_click=rng.choice(["opening", "safe"]))
    ever_flagged = set()
    for _ in range(200):
        if g.over:
            break
        i = rng.randrange(w * h)
        act = rng.random()
        if act < 0.6:
            g.reveal(i)
        elif act < 0.85:
            g.toggle_flag(i)
        else:
            g.chord(i)
        if g.mine is None:
            continue
        ever_flagged.update(i for i in range(w * h) if g.flag[i])
        assert g.opened == sum(g.open)
        assert g.flags == sum(g.flag)
        assert not any(g.open[i] and g.flag[i] for i in range(w * h))
        if g.status == "playing":
            assert not any(g.open[i] and g.mine[i] for i in range(w * h))
            # открытый ноль - все соседи открыты; закрытым может остаться только тот, где
            # стоял флажок, когда шла волна (как в Windows: снятый флажок клетку не открывает)
            for i in range(w * h):
                if g.open[i] and g.count[i] == 0:
                    assert all(g.open[j] or j in ever_flagged for j in g.nb[i])
        assert (g.status == "won") == (g.opened == w * h - m and g.status != "lost")
