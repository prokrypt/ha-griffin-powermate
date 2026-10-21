# ha-griffin-powermate
Home Assistant integration for the Griffin PowerMate Bluetooth knob. Uses HA's Bluetooth stack, so ESPHome Bluetooth proxies work too. Based on [powuhmate](https://github.com/prokrypt/powuhmate).

Install: add this repo as a HACS custom repository, or copy `custom_components/griffin_powermate` into your HA `config/custom_components/`, then restart. Turn the knob; HA discovers it.

Each knob action fires a `griffin_powermate_event` with `address` and `action`:
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
