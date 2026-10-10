"""Паспорт силы: файл на месте, цифры согласованы со строкой исходов, первые партии
каждой проверки пересчитываются с теми же зёрнами и дают те же исходы."""
import pytest

from game.ai.net import default_net, load_passport
from game.ai.tournament import run
from game.train.passport import AGENTS, LEVEL_NAMES, RULES, check_seed

SAMPLE = 6


@pytest.fixture(scope="module")
def passport():
    return load_passport()


def test_passport_has_every_check(passport):
    have = {(c["agent"], c["level"], c["first_click"]) for c in passport["checks"]}
    agents = [a for a in AGENTS if a != "medium" or default_net() is not None]
    assert have >= {(a, lv, r) for a in agents for lv in LEVEL_NAMES for r in RULES}


def test_numbers_match_results(passport):
    for c in passport["checks"]:
        assert len(c["results"]) == c["games"]
        assert c["results"].count("W") == c["wins"]
        assert abs(c["win_rate"] - c["wins"] / c["games"]) < 1e-4


def test_strong_beats_novice_everywhere(passport):
    by = {(c["agent"], c["level"], c["first_click"]): c["win_rate"] for c in passport["checks"]}
    for lv in LEVEL_NAMES:
        for r in RULES:
            assert by[("strong", lv, r)] > by[("novice", lv, r)]


@pytest.mark.slow
@pytest.mark.parametrize("agent", AGENTS)
def test_sample_recomputed_with_same_seeds(passport, agent):
    if agent == "medium" and default_net() is None:
        pytest.skip("сеть не обучена")
    for c in passport["checks"]:
        if c["agent"] != agent or c["level"] == "expert" and agent == "medium":
            continue
        assert c["seed"] == check_seed(agent, c["level"], c["first_click"])
        r = run(agent, c["level"], SAMPLE, seed=c["seed"], first_click=c["first_click"],
                indices=range(SAMPLE))
        assert r["results"] == c["results"][:SAMPLE], (agent, c["level"], c["first_click"])
