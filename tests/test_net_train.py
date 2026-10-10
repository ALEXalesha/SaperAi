"""Сеть и обучение: вход, симметрии, градиент учит, файл, данные от решателя."""
import random

import numpy as np

from aikit.nn.losses import sigmoid
from aikit.nn.optim import Adam
from game.ai import solver
from game.ai.net import FEATURES, MineNet, encode, encode_cells, symmetry
from game.core.board import FLAG, HIDDEN, Observation
from game.train.data import game_positions, generate
from game.train.fit import Trainer, evaluate, split


def test_encode_channels():
    obs = Observation.parse(["#1", "F0"], 1)
    x, hidden = encode([obs])
    assert x.shape == (1, 2, 2, FEATURES)
    assert hidden[0].tolist() == [[True, False], [True, False]]
    assert x[0, 0, 0, 0] == 1 and x[0, 1, 0, 0] == 1          # флажок - тоже закрыта
    assert x[0, 0, 1, 2] == 1 and x[0, 1, 1, 1] == 1          # «1» и «0»
    assert x[0, 0, 0, 1:10].sum() == 0
    assert np.allclose(x[0, :, :, 10], 0.5)                   # 1 мина на 2 закрытые


def test_symmetry_is_permutation_and_consistent():
    a = np.arange(2 * 3 * 4).reshape(1, 3, 4, 2)
    seen = set()
    for k in range(8):
        s = symmetry(a, k)
        assert sorted(s.reshape(-1)) == sorted(a.reshape(-1))
        seen.add(s.tobytes() + bytes(s.shape))
    assert len(seen) == 8


def test_net_any_board_size():
    net = MineNet(8, 2)
    for w, h in ((9, 9), (30, 16), (5, 3)):
        p = net.probabilities(Observation(w, h, 3, [HIDDEN] * (w * h)))
        assert len(p) == w * h and all(0 < q < 1 for q in p)


def test_net_learns_tiny_set():
    rng = random.Random(0)
    data = []
    while len(data) < 40:
        data += game_positions(9, 9, 10, rng.randrange(10 ** 6))
    cells = np.stack([c for c, _ in data[:40]])
    probs = np.stack([p for _, p in data[:40]]).astype(np.float32)
    x, hidden = encode_cells(cells, np.full(40, 10, np.float32))
    net = MineNet(16, 3, seed=1)
    opt = Adam(net.params(), lr=3e-3)
    first = net.train_step(x, probs, hidden)
    opt.step()
    for _ in range(150):
        last = net.train_step(x, probs, hidden)
        opt.step()
    assert last < first * 0.8


def test_save_load_roundtrip(tmp_path):
    net = MineNet(8, 3, seed=2)
    path = str(tmp_path / "n.npz")
    net.save(path)
    net2 = MineNet.load(path)
    obs = Observation.parse(["#1#", "111", "000"], 1)
    assert net.probabilities(obs) == net2.probabilities(obs)


def test_positions_carry_exact_solver_probabilities():
    pos = game_positions(9, 9, 10, seed=5)
    assert pos
    for cells, probs in pos[:10]:
        obs = Observation(9, 9, 10, [int(v) for v in cells.reshape(-1)])
        a = solver.analyze(obs)
        want = np.array([p if p is not None else 0.0 for p in a.probs]).reshape(9, 9)
        assert np.allclose(probs.astype(np.float64), want, atol=2e-3)
        assert set(np.unique(cells[cells < 0])) <= {-1}


def test_generate_shapes():
    r = generate(("beginner", 3, 7))
    n = len(r["cells"])
    assert n > 0 and r["cells"].shape == (n, 9, 9) and r["probs"].shape == (n, 9, 9)
    assert (r["mines"] == 10).all()


def test_trainer_snapshot_resume(tmp_path):
    r = generate(("beginner", 4, 3))
    data = {"beginner": (r["cells"], r["probs"], r["mines"])}
    train, val = split(data, frac=0.2)
    t = Trainer(str(tmp_path), channels=8, depth=2, batch=8)
    t.fit(train, val, steps=6, eval_every=3)
    t2 = Trainer(str(tmp_path), channels=8, depth=2, batch=8)
    assert t2.resume() and t2.step == 6 and t2.opt.t == t.opt.t
    for (_, a, _), (_, b, _) in zip(t.net.params(), t2.net.params()):
        assert np.array_equal(a, b)
    ev = evaluate(t2.net, val)
    assert 0 <= ev["mae"] <= 1 and 0 <= ev["best_pick"] <= 1


def test_flag_value_kept_hidden_in_encoding():
    x1, _ = encode([Observation(2, 1, 1, [FLAG, 1])])
    x2, _ = encode([Observation(2, 1, 1, [HIDDEN, 1])])
    assert np.array_equal(x1, x2)
    assert sigmoid(np.array([0.0]))[0] == 0.5
