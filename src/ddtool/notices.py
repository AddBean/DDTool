from __future__ import annotations

import logging
from collections.abc import Callable


class Reporter:
    def __init__(self, sink: Callable[[str, str], None] | None = None) -> None:
        self.sink = sink

    def info(self, message: str) -> None:
        if self.sink is not None:
            self.sink("info", message)
        else:
            logging.getLogger(__name__).info(message)

    def error(self, message: str) -> None:
        if self.sink is not None:
            self.sink("error", message)
        else:
            logging.getLogger(__name__).error(message)
