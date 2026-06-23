from typing import Protocol


class Detector(Protocol):
    def score(self, sample: object) -> float: ...
