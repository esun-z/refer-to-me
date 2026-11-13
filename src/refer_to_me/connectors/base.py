"""Connector abstraction. New message sources implement start/stop and push
IncomingMessage into the sink (returns False when the pipeline queue is full).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from refer_to_me.core.message import IncomingMessage

MessageSink = Callable[[IncomingMessage], bool]
StatusCallback = Callable[[str, str], None]


class Connector(ABC):
    name: str = "connector"

    def __init__(self, sink: MessageSink, on_status: StatusCallback | None = None):
        self._sink = sink
        self._on_status = on_status or (lambda state, detail: None)

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def _status(self, state: str, detail: str = "") -> None:
        self._on_status(state, detail)
