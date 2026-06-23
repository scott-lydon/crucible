from typing import Protocol


class Adversary(Protocol):
    def mutate(self, sample: object, score: float) -> object | None: ...
