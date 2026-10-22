class TurnGrouper:
    """Fire a click at once after a pause; group same-direction clicks closer than `gap` into one event,
    sent after `gap` of quiet, `max_wait` after the group started, or when the gesture changes."""

    def __init__(self, loop, gap, max_wait, emit) -> None:
        self._loop = loop
        self._gap = gap
        self._max_wait = max_wait
        self._emit = emit  # emit(action, steps)
        self._action = None
        self._steps = 0
        self._last = float("-inf")
        self._started = None
        self._handle = None

    def add(self, action: str) -> None:
        now = self._loop.time()
        quiet = now - self._last >= self._gap
        self._last = now
        if action != self._action:
            self.flush()
        if quiet and not self._steps:
            self._emit(action, 1)
            return
        if not self._steps:
            self._action, self._started = action, now
        self._steps += 1
        if self._handle:
            self._handle.cancel()
        self._handle = self._loop.call_at(min(now + self._gap, self._started + self._max_wait), self.flush)

    def flush(self) -> None:
        if self._handle:
            self._handle.cancel()
            self._handle = None
        if self._steps:
            self._emit(self._action, self._steps)
        self._action, self._steps = None, 0
