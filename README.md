# BF821 Chicken Coop Door — Home Assistant integration

Drives a **BF821** solar-powered automatic chicken coop door over BLE, including
through an ESPHome Bluetooth proxy. The vendor app (Zhicase Pet Door) is not
required and is not used.

The BLE protocol was recovered by decompiling the vendor APK; the complete wire
format is documented in [`apk-re/PROTOCOL.md`](apk-re/PROTOCOL.md).

## Entities

| Entity | Type | Notes |
|---|---|---|
| Door | `cover` | Open / Close / Stop (pause) |
| Light mode | `switch` | Opens above ~300 lux, closes below ~100 lux |
| Open schedule / Close schedule | `switch` | Enable the timed movements |
| Open time / Close time | `time` | When those movements happen |
| Lamp | `switch` | Write-only — the door never reports lamp state |

## Installation

**HACS** → Custom repositories → add this repo as an *Integration* → install →
restart Home Assistant.

**Manual**: copy `custom_components/bf821_door/` into your HA `config/custom_components/`
and restart.

The door is then discovered automatically via Bluetooth (it advertises as
`BF821`), or add it with **Settings → Devices & services → Add integration →
BF821**.

## How it behaves, and why

**It polls; it does not hold the connection.** Every few minutes (default 5,
configurable) it connects, reads status, and disconnects. Two reasons:

- the door is solar powered, and a held link costs meaningfully more than
  advertising;
- the door accepts exactly **one** BLE connection at a time, and a wedged link
  on a single-link peripheral can need a physical power cycle — at a coop nobody
  is standing next to. Every connect/disconnect cycle is self-healing.

**State is read, never assumed.** The door moves on its own on both light and
timer triggers, so the last command Home Assistant sent says nothing about where
the door is. Position always comes from the door's own status frame.

**The clock is re-sent on every connection.** The door's settings and RTC are
wiped whenever the solar panel loses power, so nothing is assumed to have
persisted.

## Known limitations

These are properties of the device, not of the integration:

- **Open/closed only.** The door reports a binary state — no position percentage,
  and no "currently moving" flag. `opening` / `closing` are inferred from the
  command just sent and expire after 60 s.
- **The lamp has no readback.** `switch.lamp` is an assumed state.
- **One connection at a time.** If a phone running the vendor app is connected,
  Home Assistant cannot connect, and vice versa.
- **Autonomous movement is seen late.** If the door opens on its own light
  trigger, HA notices at the next poll, not immediately.
- **No app fallback.** Once HA is the controller, if the BLE path breaks there is
  no remote fallback — only the physical controls on the unit, and someone
  present to use them.

## Development

The wire format is pure and dependency-free, so it can be tested without a Home
Assistant install:

```bash
python -m pytest tests/test_protocol.py -v
```
