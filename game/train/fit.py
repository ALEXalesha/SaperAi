"""Обучение сети на позициях от решателя: пачки одного размера, случайная симметрия поля,
Adam, проверка на отложенных позициях, снимок для продолжения с места."""
import glob
import os
import time

import numpy as np

from aikit.nn.losses import sigmoid
from aikit.nn.optim import Adam
from aikit.trainlog import TrainLog, load_snapshot, save_snapshot
from game.ai.net import MineNet, encode_cells, symmetry


def load_data(work):
    """Все куски данных из work/data: {размер: (cells, probs, mines)}."""
    parts = {}
    for path in sorted(glob.glob(os.path.join(work, "data", "*.npz"))):
        with np.load(path) as d:
            name = str(d["name"])
            parts.setdefault(name, []).append((d["cells"], d["probs"], d["mines"]))
    out = {}
    for name, items in parts.items():
        cells = np.concatenate([c for c, _, _ in items])
        if len(cells):
            out[name] = (cells, np.concatenate([p for _, p, _ in items]), np.concatenate([m for _, _, m in items]))
    return out


def split(data, frac=0.05, seed=0, cap=500):
    """Отложенные позиции для проверки: frac каждого размера (не больше cap) после
    перемешивания."""
    rng = np.random.default_rng(seed)
    train, val = {}, {}
    for name, (c, p, m) in data.items():
        idx = rng.permutation(len(c))
        k = max(1, min(cap, int(len(c) * frac)))
        v, t = idx[:k], idx[k:]
        train[name] = (c[t], p[t], m[t])
        val[name] = (c[v], p[v], m[v])
    return train, val


def evaluate(net, val, batch=256):
    """Средняя BCE и средняя абсолютная ошибка вероятности по закрытым клеткам, плюс доля
    позиций, где самая безопасная по сети клетка - и правда с наименьшим риском у решателя."""
    tot_mae = tot_n = 0.0
    hits = picks = 0
    for name, (c, p, m) in val.items():
        for s in range(0, len(c), batch):
            x, hidden = encode_cells(c[s:s + batch], m[s:s + batch].astype(np.float32))
            q = sigmoid(net.logits(x))
            t = p[s:s + batch].astype(np.float32)
            err = np.abs(q - t) * hidden
            tot_mae += float(err.sum())
            tot_n += float(hidden.sum())
            qm = np.where(hidden, q, 2.0).reshape(len(q), -1)
            tm = np.where(hidden, t, 2.0).reshape(len(t), -1)
            choice = qm.argmin(axis=1)
            best = tm.min(axis=1)
            hits += int((tm[np.arange(len(tm)), choice] <= best + 1e-6).sum())
            picks += len(tm)
    return {"mae": round(tot_mae / max(tot_n, 1), 5), "best_pick": round(hits / max(picks, 1), 4)}


class Trainer:
    def __init__(self, work, channels=24, depth=4, lr=1e-3, batch=32, seed=0):
        self.work = work
        self.snapshot_path = os.path.join(work, "snapshot.npz")
        self.log = TrainLog(os.path.join(work, "train.log"))
        self.net = MineNet(channels, depth, seed)
        self.opt = Adam(self.net.params(), lr=lr)
        self.batch = batch
        self.step = 0
        self.seconds = 0.0
        self.rng = np.random.default_rng(seed + 1)
        self.history = []

    def save(self):
        arrays = self.net.arrays()
        for k, (m, v) in enumerate(zip(self.opt.m, self.opt.v)):
            arrays[f"adam.m{k}"] = m
            arrays[f"adam.v{k}"] = v
        save_snapshot(self.snapshot_path, arrays, {"step": self.step, "seconds": self.seconds,
                                                   "adam_t": self.opt.t, "history": self.history,
                                                   "channels": self.net.channels, "depth": self.net.depth})

    def resume(self):
        snap = load_snapshot(self.snapshot_path)
        if snap is None:
            return False
        arrays, meta = snap
        self.net = MineNet(meta["channels"], meta["depth"])
        for name, arr, _ in self.net.params():
            arr[...] = arrays[name]
        self.opt = Adam(self.net.params(), lr=self.opt.lr)
        for k in range(len(self.opt.m)):
            self.opt.m[k][...] = arrays[f"adam.m{k}"]
            self.opt.v[k][...] = arrays[f"adam.v{k}"]
        self.opt.t = int(meta["adam_t"])
        self.step = int(meta["step"])
        self.seconds = float(meta["seconds"])
        self.history = list(meta.get("history", []))
        return True

    def batch_from(self, train):
        names = sorted(train)
        sizes = np.array([len(train[n][0]) for n in names], np.float64)
        name = names[self.rng.choice(len(names), p=sizes / sizes.sum())]
        c, p, m = train[name]
        idx = self.rng.integers(0, len(c), self.batch)
        k = int(self.rng.integers(0, 8))
        cells = symmetry(c[idx], k)
        target = symmetry(p[idx], k).astype(np.float32)
        x, hidden = encode_cells(cells, m[idx].astype(np.float32))
        return x, target, hidden

    def fit(self, train, val, steps, eval_every=500, lr_drop=None):
        t0 = time.perf_counter()
        base = self.seconds
        while self.step < steps:
            if lr_drop and self.step >= lr_drop:
                self.opt.lr = min(self.opt.lr, 3e-4)
            x, target, hidden = self.batch_from(train)
            loss = self.net.train_step(x, target, hidden)
            self.opt.step()
            self.step += 1
            if self.step % eval_every == 0 or self.step == steps:
                self.seconds = base + time.perf_counter() - t0
                ev = evaluate(self.net, val)
                rec = {"step": self.step, "loss": round(loss, 5), **ev, "seconds": round(self.seconds, 1)}
                self.history.append(rec)
                self.log(str(rec))
                self.save()
        self.seconds = base + time.perf_counter() - t0
        return self.history[-1] if self.history else None
