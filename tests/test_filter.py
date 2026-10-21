"""Event filter: which raw knob codes become actions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.griffin_powermate import PowerMate

ADDRESS = "00:12:92:08:2E:31"


def actions(timeline: list[tuple[float, int]]) -> list[str]:
    """Feed (seconds, code) notifications to a PowerMate; return the actions it fired."""
    hass = MagicMock()
    pm = PowerMate(hass, ADDRESS, "PowerMate")
    with (
        patch("custom_components.griffin_powermate.time.monotonic") as monotonic,
        patch("custom_components.griffin_powermate.async_dispatcher_send"),
    ):
        for at, code in timeline:
            monotonic.return_value = 1000 + at
            pm._on_notify(None, bytearray([code]))
    return [c.args[1]["action"] for c in hass.bus.async_fire.call_args_list]


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
