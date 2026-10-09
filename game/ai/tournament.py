"""Проверка силы: доля выигранных партий на каждом размере поля, партии с зёрнами.

Партия i на поле level получает зерно раскладки seed_of(seed, i) - любую партию можно
пересчитать отдельно и сверить с паспортом. Решения ИИ (выбор среди равных догадок) - от
своего генератора с тем же зерном.
"""
import random
import time

from game.core.board import LEVELS, Game


def seed_of(seed, i):
    return (int(seed) * 1_000_003 + int(i)) % (2 ** 31)


def play(agent, width, height, mines, seed, first_click="opening", no_guess=False, max_steps=10_000):
    """Одна партия до конца. Возвращает словарь: won, guesses, steps, seconds, exact."""
    g = Game(width, height, mines, seed=seed, first_click=first_click, no_guess=no_guess)
    rng = random.Random(seed ^ 0x5A5A)
    t0 = time.perf_counter()
    guesses = steps = 0
    exact = True
    while not g.over and steps < max_steps:
        move = agent.choose(g.observe(), rng)
        steps += 1
        guesses += move.guess
        exact &= move.exact
        for i in move.cells:
            g.reveal(i)
            if g.over:
                break
    return {"won": g.status == "won", "guesses": guesses, "steps": steps,
            "seconds": time.perf_counter() - t0, "exact": exact}


def _job(args):
    level_name, agent_level, seed, i, first_click = args
    from game.ai.agents import make_agent
    agent = _AGENTS.get(agent_level)
    if agent is None:
        agent = _AGENTS[agent_level] = make_agent(agent_level)
    w, h, m = LEVELS[level_name]
    r = play(agent, w, h, m, seed_of(seed, i), first_click)
    return "W" if r["won"] else "L", r["guesses"], r["seconds"], r["exact"]


_AGENTS = {}


def run(agent_level, level_name, games, seed=2026, first_click="opening", processes=1, indices=None):
    """Строка исходов 'WL...' и сводка. processes > 1 - по процессам (spawn), у каждого
    один поток BLAS."""
    idx = list(range(games)) if indices is None else list(indices)
    jobs = [(level_name, agent_level, seed, i, first_click) for i in idx]
    t0 = time.time()
    if processes > 1:
        import multiprocessing as mp
        from aikit.trainlog import limit_threads
        limit_threads(1, force=True)
        with mp.get_context("spawn").Pool(processes) as pool:
            out = pool.map(_job, jobs, chunksize=max(1, len(jobs) // (processes * 8)))
    else:
        out = [_job(j) for j in jobs]
    results = "".join(o[0] for o in out)
    wins = results.count("W")
    return {"agent": agent_level, "level": level_name, "first_click": first_click, "seed": seed,
            "games": len(results), "wins": wins, "win_rate": round(wins / max(1, len(results)), 4),
            "avg_guesses": round(sum(o[1] for o in out) / max(1, len(out)), 3),
            "approximate_games": sum(not o[3] for o in out),
            "max_game_seconds": round(max([o[2] for o in out] or [0]), 3),
            "seconds": round(time.time() - t0, 1), "results": results}
