"""Ход ИИ, подсказка и «Мысли ИИ» в отдельном потоке: окно не подвисает.

Каждый запрос получает номер (token); ответ со старым номером (новая партия, ход
человека) окно выбрасывает. В поток уходит только Observation - ИИ не может подсмотреть
мины. При закрытии окна потоки ждут не дольше 2 секунд (контракт aikit): решатель
ограничен бюджетом узлов, поэтому долго не считает.
"""
import random
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal

from game.ai import solver
from game.ai.agents import make_agent, pick_guess


def thoughts(obs, level):
    """Вероятности для тепловой карты так, как их видит ИИ этого уровня."""
    if level == "medium":
        from game.ai.net import default_net
        net = default_net()
        if net is not None:
            return {"probs": net.probabilities(obs), "source": "net", "exact": False}
    if level == "novice":
        known = solver.simple_known(obs)
        probs = [None] * len(obs.cells)
        for i, k in known.items():
            probs[i] = float(k)
        return {"probs": probs, "source": "novice", "exact": True}
    a = solver.analyze(obs)
    return {"probs": a.probs, "source": "solver", "exact": a.exact}


def hint(obs):
    """Подсказка всегда от точного решателя: безопасная клетка или наименьший риск."""
    if all(v < 0 for v in obs.cells):
        from game.ai.agents import first_cell
        return {"cell": first_cell(obs), "safe": True, "p": 0.0}
    a = solver.analyze(obs)
    if a.safe:
        return {"cell": a.safe[0], "safe": True, "p": 0.0}
    i = pick_guess(obs, a.probs, random.Random(0))
    return {"cell": i, "safe": False, "p": a.probs[i]}


class _Job(QThread):
    done = Signal(int, str, object)

    def __init__(self, token, kind, fn, parent=None):
        super().__init__(parent)
        self.token = token
        self.kind = kind
        self.fn = fn
        self.stop_event = threading.Event()

    def run(self):
        try:
            payload = self.fn()
        except Exception as e:  # noqa: BLE001 - ошибку покажет окно, поток не падает молча
            payload = e
        if not self.stop_event.is_set():
            self.done.emit(self.token, self.kind, payload)


class AiController(QObject):
    """request_move / request_thoughts / request_hint. Ответ - сигнал ready(token, вид,
    результат или исключение)."""

    ready = Signal(int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = []

    def _start(self, token, kind, fn):
        self.jobs = [j for j in self.jobs if j.isRunning()]
        job = _Job(token, kind, fn, self)
        job.done.connect(self.ready)
        self.jobs.append(job)
        job.start()
        return job

    def request_move(self, token, obs, level, seed):
        agent = make_agent(level)
        return self._start(token, "move", lambda: agent.choose(obs, random.Random(seed)))

    def request_thoughts(self, token, obs, level):
        return self._start(token, "thoughts", lambda: thoughts(obs, level))

    def request_hint(self, token, obs):
        return self._start(token, "hint", lambda: hint(obs))

    def cancel(self):
        for j in self.jobs:
            j.stop_event.set()

    def busy(self):
        self.jobs = [j for j in self.jobs if j.isRunning()]
        return bool(self.jobs)

    def shutdown(self, timeout_ms=2000):
        self.cancel()
        deadline = time.monotonic() + timeout_ms / 1000
        for j in self.jobs:
            j.wait(max(0, int((deadline - time.monotonic()) * 1000)))
        return not self.busy()
