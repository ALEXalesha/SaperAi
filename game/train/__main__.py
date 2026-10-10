"""Обучение сети по команде:

    python -m game.train data --games 2000 --workers 2      # позиции от решателя
    python -m game.train fit --steps 20000 --threads 2      # обучение (продолжает снимок)
    python -m game.train publish                            # сеть из снимка -> game/models

Потоки ограничены: работники данных считают по одному потоку BLAS, обучение - --threads.
Рабочая папка --work (по умолчанию %LOCALAPPDATA%\\SaperAi\\train - не в синхронизируемой
папке проекта): куски данных, журнал train.log и снимок.
"""
import os
import sys


def default_work():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SaperAi", "train")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m game.train")
    ap.add_argument("cmd", choices=("data", "fit", "publish"))
    ap.add_argument("--work", default=default_work())
    ap.add_argument("--games", type=int, default=2000, help="партий на каждый размер поля")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--channels", type=int, default=24)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--eval-every", type=int, default=500)
    args = ap.parse_args(argv)

    from aikit.trainlog import limit_threads
    limit_threads(1 if args.cmd == "data" else args.threads, force=True)
    import json
    import time

    import numpy as np

    os.makedirs(args.work, exist_ok=True)
    if args.cmd == "data":
        import multiprocessing as mp

        from game.train.data import CONFIGS, generate
        out_dir = os.path.join(args.work, "data")
        os.makedirs(out_dir, exist_ok=True)
        chunk = 50
        jobs = []
        for k, name in enumerate(CONFIGS):
            for c in range(0, args.games, chunk):
                jobs.append((name, min(chunk, args.games - c), args.seed * 1_000_003 + k * 10_007 + c))
        t0 = time.time()
        n = 0
        with mp.get_context("spawn").Pool(args.workers) as pool:
            for r, job in zip(pool.imap(generate, jobs), jobs):
                path = os.path.join(out_dir, f"{job[0]}-{job[2]}.npz")
                np.savez_compressed(path, name=np.array(r["name"]), cells=r["cells"], probs=r["probs"],
                                    mines=r["mines"])
                n += len(r["cells"])
                print(f"{job[0]}: +{len(r['cells'])} позиций, всего {n}, {time.time() - t0:.0f} с", flush=True)
        meta = os.path.join(args.work, "data.json")
        prev = json.load(open(meta, encoding="utf-8")) if os.path.exists(meta) else {"games": 0, "seconds": 0}
        json.dump({"games": prev["games"] + args.games * len(CONFIGS),
                   "seconds": round(prev["seconds"] + time.time() - t0, 1)},
                  open(meta, "w", encoding="utf-8"))
        return 0

    from game.train.fit import Trainer, load_data, split
    t = Trainer(args.work, args.channels, args.depth, batch=args.batch)
    if args.cmd == "publish":
        if not t.resume():
            print("снимка нет")
            return 1
        t.net.save()
        print(f"сеть шага {t.step} -> game/models/saper-net.npz")
        return 0
    if t.resume():
        print(f"продолжаю с шага {t.step}", flush=True)
    data = load_data(args.work)
    train, val = split(data)
    print({k: len(v[0]) for k, v in train.items()}, flush=True)
    t.fit(train, val, args.steps, eval_every=args.eval_every, lr_drop=int(args.steps * 0.75))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.exit(main())
