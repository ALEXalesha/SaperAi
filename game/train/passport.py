"""Паспорт силы и модели (spec §3): доля выигранных партий на каждом размере поля для
каждого уровня ИИ и обоих правил первого клика, партии с зёрнами.

    python -m game.train.passport --games 10000 --processes 2
    python -m game.train.passport --games 10000 --only medium     # пересчитать один уровень
    python -m game.train.passport --force                         # всё заново

Файл пишется после каждой проверки; уже посчитанные с тем же числом партий пропускаются -
прерванный прогон продолжается с места.

Результат - game/models/saper-passport.json. Строка исходов каждой проверки записана
целиком: тесты пересчитывают первые партии с теми же зёрнами и сверяют.
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402

AGENTS = ("novice", "medium", "strong")
LEVEL_NAMES = ("beginner", "intermediate", "expert")
RULES = ("opening", "safe")


def check_seed(agent, level, rule):
    """Зерно проверки: одно и то же поле для всех уровней ИИ - сравнение честное."""
    return 1000 + 10 * LEVEL_NAMES.index(level) + RULES.index(rule)


def training_info(work):
    from game.ai.net import default_net
    info = {}
    net = default_net()
    if net is not None:
        info["network"] = {"kind": "conv3x3", "channels": net.channels, "depth": net.depth,
                           "features": 11, "parameters": net.n_params()}
    if work and os.path.exists(os.path.join(work, "snapshot.npz")):
        from aikit.trainlog import load_snapshot
        _, meta = load_snapshot(os.path.join(work, "snapshot.npz"))
        hist = meta.get("history", [])
        info["training"] = {"steps": meta["step"], "seconds": round(meta["seconds"], 1),
                            "last": hist[-1] if hist else None}
        data = os.path.join(work, "data.json")
        if os.path.exists(data):
            d = json.load(open(data, encoding="utf-8"))
            info["training"]["data_games"] = d["games"]
            info["training"]["data_seconds"] = d["seconds"]
        counts = os.path.join(work, "counts.json")
        if os.path.exists(counts):
            info["training"].update(json.load(open(counts, encoding="utf-8")))
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train.passport")
    ap.add_argument("--games", type=int, default=10000)
    ap.add_argument("--processes", type=int, default=2)
    ap.add_argument("--only", choices=AGENTS)
    ap.add_argument("--work", default=None, help="папка обучения (сведения о сети)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true", help="пересчитать и уже посчитанные проверки")
    args = ap.parse_args(argv)

    from aikit.storage import save_json
    from game.ai.net import PASSPORT, default_net
    from game.ai.tournament import run
    from game.version import VERSION
    out = args.out or PASSPORT
    old = {}
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            old = json.load(f)
    checks = {(c["agent"], c["level"], c["first_click"]): c for c in old.get("checks", [])}
    agents = [args.only] if args.only else [a for a in AGENTS if a != "medium" or default_net() is not None]
    order = {a: k for k, a in enumerate(AGENTS)}
    info = training_info(args.work)

    def write():
        # после КАЖДОЙ проверки, атомарно и с созданием папки: 10.10 первый прогон (≈1 ч)
        # досчитал всё и упал на записи - папки game/models ещё не было
        passport = {
            "game": "SaperAi", "version": VERSION,
            "date": datetime.date.today().isoformat(),
            "note": "доля выигранных партий; зерно поля общее для всех уровней ИИ",
            **{k: v for k, v in old.items() if k in ("network", "training")},
            **info,
            "checks": sorted(checks.values(), key=lambda c: (order[c["agent"]], LEVEL_NAMES.index(c["level"]),
                                                              RULES.index(c["first_click"]))),
        }
        if not save_json(out, passport):
            raise OSError(f"паспорт не записан: {out}")

    for agent in agents:
        for level in LEVEL_NAMES:
            for rule in RULES:
                have = checks.get((agent, level, rule))
                if have and have["games"] == args.games and not args.force:
                    continue                    # уже посчитано - прерванный прогон продолжается
                r = run(agent, level, args.games, seed=check_seed(agent, level, rule), first_click=rule,
                        processes=args.processes)
                checks[(agent, level, rule)] = r
                write()
                print(f"{agent:7} {level:12} {rule:8} {100 * r['win_rate']:5.1f}%  ({r['seconds']:.0f} с)",
                      flush=True)
    write()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.exit(main())
