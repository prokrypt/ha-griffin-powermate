# ha-griffin-powermate
Home Assistant integration for the Griffin PowerMate Bluetooth knob. Uses HA's Bluetooth stack, so ESPHome Bluetooth proxies work too. Based on [powuhmate](https://github.com/prokrypt/powuhmate).

Install: add this repo as a HACS custom repository, or copy `custom_components/griffin_powermate` into your HA `config/custom_components/`, then restart. Turn the knob; HA discovers it.

## Map gestures to actions (no YAML)
[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fprokrypt%2Fha-griffin-powermate%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgriffin_powermate%2Fpowermate_actions.yaml)

Import the blueprint, create an automation from it, pick your PowerMate, and set any action per gesture. One automation per knob, or several for different modes.

## Entities
- `event.<name>_knob`: last gesture in `event_type`.
- `light.<name>_led`: on/off, brightness, effects `blink_1`…`blink_4`. State is restored and re-sent each time the knob reconnects. Drive it from the blueprint actions, e.g. turn it on while the volume changes.
- `sensor.<name>_battery`: read on connect and every 10 min.

## Raw events
Each knob action also fires a `griffin_powermate_event` with `address` and `action`:
`press`, `release`, `cw`, `ccw`, `press_cw`, `press_ccw`, `hold_1` … `hold_6`.

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
