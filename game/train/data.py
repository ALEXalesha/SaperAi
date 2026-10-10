"""Данные для сети: позиции из партий и точная вероятность мины от решателя.

Партию ведёт сильный ИИ, но открывает по ОДНОЙ безопасной клетке за ход (а иногда все
сразу) - так позиций больше и они разнообразнее. Первый клик - случайная клетка.
Позиция, где решатель не уложился в бюджет (exact=False), в данные не идёт: цель должна
быть точной.

Позиции одного размера хранятся вместе: cells int8 (N, H, W) - видимое поле (числа и -1
у закрытых), probs float16 (N, H, W) - вероятность мины (0 у открытых), mines int16 (N,).
"""
import random

import numpy as np

from game.ai import solver
from game.ai.agents import pick_guess
from game.core.board import Game

# имя: (ширина, высота, мин от, мин до)
CONFIGS = {
    "beginner": (9, 9, 10, 10),
    "intermediate": (16, 16, 40, 40),
    "expert": (30, 16, 99, 99),
    "mixed": (16, 16, 20, 60),
}


def game_positions(width, height, mines, seed, first_click="opening", budget=solver.BUDGET):
    """Позиции одной партии: список (cells, probs) numpy-массивами (H, W)."""
    rng = random.Random(seed)
    g = Game(width, height, mines, seed=seed, first_click=first_click)
    g.reveal(rng.randrange(width * height))
    out = []
    while g.status == "playing":
        obs = g.observe()
        a = solver.analyze(obs, budget=budget)
        if a.exact:
            cells = np.array(obs.cells, np.int8).reshape(height, width)
            cells[cells < 0] = -1
            probs = np.array([p if p is not None else 0.0 for p in a.probs], np.float32).reshape(height, width)
            out.append((cells, probs.astype(np.float16)))
        if a.safe:
            todo = a.safe if rng.random() < 0.3 else [rng.choice(a.safe)]
        else:
            todo = [pick_guess(obs, a.probs, rng)]
        for i in todo:
            g.reveal(i)
            if g.over:
                break
    return out


def generate(job):
    """Работник пула: (имя размера, число партий, зерно) -> словарь массивов."""
    name, games, seed = job
    w, h, lo, hi = CONFIGS[name]
    rng = random.Random(seed)
    cells, probs, mines = [], [], []
    for _ in range(games):
        m = rng.randint(lo, hi)
        rule = "opening" if rng.random() < 0.7 else "safe"
        for c, p in game_positions(w, h, m, rng.randrange(2 ** 31), rule):
            cells.append(c)
            probs.append(p)
            mines.append(m)
    if not cells:
        return {"name": name, "cells": np.zeros((0, h, w), np.int8),
                "probs": np.zeros((0, h, w), np.float16), "mines": np.zeros(0, np.int16)}
    return {"name": name, "cells": np.stack(cells), "probs": np.stack(probs),
            "mines": np.array(mines, np.int16)}
