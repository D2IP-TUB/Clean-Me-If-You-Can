from collections import defaultdict


class StatCounter(defaultdict):
    def __init__(self):
        super().__init__(int)

    def inc(self, key: str, value: int = 1):
        self[key] += value

    def filter(self, prefix_filter: str) -> dict:
        return {k: v for k, v in self.items() if k.startswith(prefix_filter)}

    def sum_prefix(self, prefix: str) -> int:
        return sum(v for k, v in self.items() if k.startswith(prefix))
