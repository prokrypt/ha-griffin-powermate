DOMAIN = "griffin_powermate"
EVENT = "griffin_powermate_event"
LOCAL_NAME = "PowerMate Bluetooth"
# matched too, in case HA hears the knob without its name
UUID_SERVICE = "25598cf7-4240-40a6-9910-080f19f91ebc"
UUID_READ = "9cf53570-ddd9-47f3-ba63-09acefc60415"
UUID_LED = "847d189e-86ee-4bd2-966f-800832b1259d"

ACTIONS = {
    0x65: "press",
    0x66: "release",
    0x67: "ccw",
    0x68: "cw",
    0x69: "press_ccw",
    0x70: "press_cw",
    0x72: "hold_1",
    0x73: "hold_2",
    0x74: "hold_3",
    0x75: "hold_4",
    0x76: "hold_5",
    0x77: "hold_6",
}
# the button double-fires press/release; drop a repeat within this many seconds
DEBOUNCE = 1.0


def is_duplicate(code, last_code, elapsed):
    return code in (0x65, 0x66) and code == last_code and elapsed < DEBOUNCE


# letting go after a press-turn can send a stray press (button bounce) or cw/ccw;
# drop those up to this many seconds after the last press_cw/press_ccw step (one seen at 1.0s)
PRESS_TURN = (0x69, 0x70)
PRESS_TURN_QUIET = 1.0


def is_press_turn_tail(code, elapsed):
    return code in (0x65, 0x67, 0x68) and elapsed <= PRESS_TURN_QUIET


# turn clicks closer than TURN_GAP are sent as one event with a step count
TURNS = (0x67, 0x68, 0x69, 0x70)
TURN_GAP = 0.2
TURN_MAX_WAIT = 0.5

UUID_BATTERY = "50f09cc9-fe1d-4c79-a962-b3a7cd3e5584"  # notify only; the knob has no 0x2A19
BATTERY_INTERVAL = 600  # seconds between battery refreshes while connected

# LED byte: 80 off, A1..BF dim..bright, C0..FF blink at different speeds
LED_OFF = 0x80
EFFECTS = {"blink_1": 0xC0, "blink_2": 0xD0, "blink_3": 0xE0, "blink_4": 0xF0}


def led_byte(is_on, brightness, effect):
    if not is_on:
        return LED_OFF
    if effect in EFFECTS:
        return EFFECTS[effect]
    return 0xA1 + round((max(brightness, 1) - 1) * 30 / 254)
