"""Event filter: which raw knob codes become actions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.griffin_powermate import PowerMate

ADDRESS = "00:12:92:08:2E:31"


class FakeLoop:
    """Just enough of an event loop for TurnGrouper, on a clock the test sets."""

    def __init__(self) -> None:
        self.now = 0.0
        self.timers: list[list] = []

    def time(self) -> float:
        return self.now

    def call_at(self, when: float, callback):
        timer = [when, callback]
        self.timers.append(timer)
        return MagicMock(cancel=lambda: timer in self.timers and self.timers.remove(timer))

    def advance(self, to: float) -> None:
        while due := [t for t in self.timers if t[0] <= to]:
            timer = min(due, key=lambda t: t[0])
            self.timers.remove(timer)
            self.now = timer[0]
            timer[1]()
        self.now = to


def fired(timeline: list[tuple[float, int]]) -> list[tuple[str, int]]:
    """Feed (seconds, code) notifications to a PowerMate; return the (action, steps) it fired."""
    hass = MagicMock()
    hass.loop = loop = FakeLoop()
    pm = PowerMate(hass, ADDRESS, "PowerMate")
    with (
        patch("custom_components.griffin_powermate.time.monotonic") as monotonic,
        patch("custom_components.griffin_powermate.async_dispatcher_send"),
    ):
        for at, code in timeline:
            loop.advance(at)
            monotonic.return_value = 1000 + at
            pm._on_notify(None, bytearray([code]))
        loop.advance(at + 10)
    return [(c.args[1]["action"], c.args[1]["steps"]) for c in hass.bus.async_fire.call_args_list]


def actions(timeline: list[tuple[float, int]]) -> list[str]:
    return [action for action, steps in fired(timeline) for _ in range(steps)]


def test_stray_press_after_press_turn_is_dropped() -> None:
    # recorded 2026-10-21: press_ccw steps, then a press 1.0s after the last one on release
    assert actions([(0.0, 0x69), (0.16, 0x69), (0.32, 0x69), (0.48, 0x69), (0.72, 0x69), (1.72, 0x65)]) == [
        "press_ccw"
    ] * 5


def test_stray_turn_after_press_turn_is_dropped() -> None:
    assert actions([(0.0, 0x70), (0.1, 0x70), (0.5, 0x68), (1.0, 0x67)]) == ["press_cw"] * 2


def test_window_runs_from_the_last_press_turn_step() -> None:
    assert actions([(0.0, 0x70), (0.9, 0x70), (1.9, 0x65)]) == ["press_cw", "press_cw"]


def test_events_after_the_window_pass() -> None:
    assert actions([(0.0, 0x69), (1.1, 0x65), (3.0, 0x68), (3.1, 0x68)]) == ["press_ccw", "press", "cw", "cw"]


def test_plain_presses_and_turns_pass() -> None:
    # recorded: single presses 1.4-2.6s apart, turns 40-200ms apart
    assert actions([(0.0, 0x65), (1.36, 0x65), (2.96, 0x65), (4.0, 0x67), (4.04, 0x67), (4.2, 0x68)]) == [
        "press",
        "press",
        "press",
        "ccw",
        "ccw",
        "cw",
    ]


def test_hold_codes_are_not_filtered() -> None:
    assert actions([(0.0, 0x70), (0.5, 0x72)]) == ["press_cw", "hold_1"]


def test_first_turn_fires_at_once() -> None:
    hass = MagicMock()
    hass.loop = FakeLoop()
    pm = PowerMate(hass, ADDRESS, "PowerMate")
    with patch("custom_components.griffin_powermate.async_dispatcher_send"):
        pm._on_notify(None, bytearray([0x68]))
    assert hass.bus.async_fire.call_args.args[1]["action"] == "cw"


def test_fast_turns_are_grouped_until_a_pause() -> None:
    assert fired([(0.0, 0x68), (0.05, 0x68), (0.1, 0x68), (0.15, 0x68), (0.6, 0x68)]) == [
        ("cw", 1),
        ("cw", 3),
        ("cw", 1),
    ]


def test_a_long_spin_is_sent_at_least_every_max_wait() -> None:
    # clicks every 50ms for 1.2s: first at once, then groups capped at 0.5s
    out = fired([(i * 0.05, 0x67) for i in range(25)])
    assert out[0] == ("ccw", 1) and len(out) >= 3 and sum(steps for _, steps in out) == 25


def test_direction_change_sends_the_group_first() -> None:
    assert fired([(0.0, 0x68), (0.05, 0x68), (0.1, 0x68), (0.15, 0x67), (0.2, 0x67)]) == [
        ("cw", 1),
        ("cw", 2),
        ("ccw", 2),
    ]


def test_button_flushes_pending_turns_first() -> None:
    assert fired([(0.0, 0x68), (0.05, 0x68), (0.1, 0x72)]) == [("cw", 1), ("cw", 1), ("hold_1", 1)]
