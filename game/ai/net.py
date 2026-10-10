"""Сеть среднего уровня: по видимому полю - вероятность мины в каждой закрытой клетке.

Свёрточная, на слоях aikit.nn (numpy). Размер поля не зашит: свёртки 3x3 с нулями за
краем работают на 9x9 и на 30x16 одними и теми же весами. Учится на позициях из партий,
цель - точная вероятность от решателя (game.ai.solver), потеря - двоичная перекрёстная
энтропия только по закрытым клеткам.

Вход - по клетке FEATURES каналов (раскладка (B, H, W, C)):
  0      закрыта (флажок - тоже закрыта: сеть, как и решатель, флажкам не верит);
  1..9   открыта и показывает 0..8 (одна единица);
  10     плотность мин: сколько мин на закрытую клетку осталось по счётчику поля
         (общее число мин минус ничего - сеть сама не знает, где мины, и флажки не вычитает).
За краем поля все каналы - нули: так сеть видит стену.
"""
import json
import os

import numpy as np

from aikit.nn import io as nnio
from aikit.nn.layers import Conv3x3, Dense, ReLU, Sequential
from aikit.nn.losses import bce, sigmoid

FEATURES = 11
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
MODEL = os.path.join(MODEL_DIR, "saper-net.npz")
PASSPORT = os.path.join(MODEL_DIR, "saper-passport.json")


def encode(obs_list):
    """Пачка наблюдений одного размера -> (B, H, W, FEATURES) float32 и маска закрытых."""
    w, h = obs_list[0].width, obs_list[0].height
    cells = np.array([o.cells for o in obs_list], dtype=np.int16).reshape(len(obs_list), h, w)
    return encode_cells(cells, np.array([o.mines for o in obs_list], dtype=np.float32))


def encode_cells(cells, mines):
    """cells (B, H, W): числа 0..8 и отрицательные у закрытых; mines (B,) - мин на поле."""
    B, H, W = cells.shape
    x = np.zeros((B, H, W, FEATURES), np.float32)
    hidden = cells < 0
    x[..., 0] = hidden
    num = np.where(hidden, 0, cells).astype(np.int64)
    oh = np.zeros((B, H, W, 9), np.float32)
    np.put_along_axis(oh, num[..., None], 1.0, axis=-1)
    x[..., 1:10] = oh * (~hidden)[..., None]
    n_hidden = hidden.reshape(B, -1).sum(axis=1).astype(np.float32)
    density = np.clip(mines / np.maximum(n_hidden, 1.0), 0.0, 1.0)
    x[..., 10] = density[:, None, None]
    return x, hidden


def symmetry(a, k):
    """Одна из 8 симметрий поля (повороты и отражения) по осям H, W массива (B, H, W, ...)."""
    if k & 4:
        a = np.swapaxes(a, 1, 2)
    if k & 1:
        a = a[:, ::-1]
    if k & 2:
        a = a[:, :, ::-1]
    return np.ascontiguousarray(a)


class MineNet:
    def __init__(self, channels=24, depth=4, seed=0):
        rng = np.random.default_rng(seed)
        layers = [Conv3x3(FEATURES, channels, rng), ReLU()]
        for _ in range(depth - 1):
            layers += [Conv3x3(channels, channels, rng), ReLU()]
        layers.append(Dense(channels, 1, rng))
        self.model = Sequential(layers)
        self.channels, self.depth = channels, depth

    def params(self):
        return self.model.params()

    def n_params(self):
        return int(sum(p.size for _, p, _ in self.params()))

    def logits(self, x):
        return self.model.forward(x)[..., 0]

    def train_step(self, x, target, mask):
        """Одна пачка: потеря BCE по закрытым клеткам, градиенты в слоях."""
        z = self.logits(x)
        loss, g = bce(z, target, mask.astype(np.float32))
        self.model.backward(g[..., None])
        return loss

    def probabilities(self, obs):
        """Список вероятностей по клеткам (None у открытых) - как у решателя."""
        x, hidden = encode([obs])
        p = sigmoid(self.logits(x))[0].reshape(-1)
        hid = hidden[0].reshape(-1)
        return [float(p[i]) if hid[i] else None for i in range(len(hid))]

    # --- файл ---

    def arrays(self):
        out = {name: arr for name, arr, _ in self.params()}
        out["meta.channels"] = np.array(self.channels)
        out["meta.depth"] = np.array(self.depth)
        return out

    def save(self, path=MODEL):
        # папки game/models в свежем клоне может не быть (git пустые папки не хранит)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        nnio.save(path, self.arrays())

    @classmethod
    def load(cls, path=MODEL):
        a = nnio.load(path)
        net = cls(int(a["meta.channels"]), int(a["meta.depth"]))
        for name, arr, _ in net.params():
            if a[name].shape != arr.shape:
                raise ValueError(f"{name}: в файле {a[name].shape}, в сети {arr.shape}")
            arr[...] = a[name]
        return net


_DEFAULT = {}


def default_net():
    """Обученная сеть из game/models или None, если её ещё нет."""
    if "net" not in _DEFAULT:
        try:
            _DEFAULT["net"] = MineNet.load(MODEL)
        except (OSError, KeyError, ValueError):
            _DEFAULT["net"] = None
    return _DEFAULT["net"]


def load_passport(path=PASSPORT):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
