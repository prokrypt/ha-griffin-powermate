# ha-griffin-powermate
Home Assistant integration for the Griffin PowerMate Bluetooth knob. Uses HA's Bluetooth stack, so ESPHome Bluetooth proxies work too. Based on [powuhmate](https://github.com/prokrypt/powuhmate).

Install: add this repo as a HACS custom repository, or copy `custom_components/griffin_powermate` into your HA `config/custom_components/`, then restart. The knob shows up under Settings > Devices & services > Discovered as soon as HA hears it. An idle knob only advertises in bursts of about 10s, minutes apart, so this can take a few minutes.

To add it by hand: Add integration > Griffin PowerMate Bluetooth, then pick the knob from the list or type its Bluetooth address (`00:12:92:xx:xx:xx`, printed by `bluetoothctl scan on`). A typed address works even if HA has not heard the knob yet; it connects the next time the knob advertises.

## Troubleshooting
- Nothing discovered: HA needs a Bluetooth adapter or ESPHome Bluetooth proxy within range of the knob. Check that `bluetoothctl scan on` on the HA host (or the proxy's log) shows `PowerMate Bluetooth`.
- If another machine is connected to the knob (e.g. running powuhmate), HA can't use it. Stop the other tool first.
- Connection problems: add `custom_components.griffin_powermate: debug` under `logger:` `logs:` in `configuration.yaml` and look for `PowerMate <address>` lines.

## Map gestures to actions (no YAML)
[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fprokrypt%2Fha-griffin-powermate%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgriffin_powermate%2Fpowermate_actions.yaml)

Import the blueprint, create an automation from it, pick your PowerMate, and set any action per gesture. One automation per knob, or several for different modes.

## Entities
- `event.<name>_knob`: last gesture in `event_type`, click count in `steps`.
- `light.<name>_led`: on/off, brightness, effects `blink_1`…`blink_4`. State is restored and re-sent each time the knob reconnects. Drive it from the blueprint actions, e.g. turn it on while the volume changes.
- `sensor.<name>_battery`: read on connect and every 10 min.

## Raw events
Each knob action also fires a `griffin_powermate_event` with `address`, `action` and `steps`:
`press`, `release`, `cw`, `ccw`, `press_cw`, `press_ccw`, `hold_1` … `hold_6`.

A turn click fires at once. Further clicks in the same direction less than 200ms apart are grouped into one event whose `steps` is the click count, sent after 200ms without a click or 500ms at most. A fast spin then makes a few events instead of dozens, so the automation can apply the whole change at once, e.g. `brightness_step_pct: "{{ 2 * trigger.to_state.attributes.steps }}"`. The blueprint runs your action once per click.

Letting go after a press-turn can make the knob send a stray `press`, `cw` or `ccw`, so those are dropped for 1s after each `press_cw`/`press_ccw` step.

```yaml
automation:
  - trigger:
      - platform: event
        event_type: griffin_powermate_event
        event_data: { action: cw }
    action:
      - service: media_player.volume_up
        target: { entity_id: media_player.living_room }
```

## Development
```sh
pip install -r requirements_test.txt
python script/ha_requirements.py > /tmp/ha_requirements.txt
pip install -r /tmp/ha_requirements.txt -c "$(python script/ha_requirements.py --constraints)"
pytest
```
