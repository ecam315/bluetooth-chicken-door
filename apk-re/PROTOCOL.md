# BF821 chicken-coop door — BLE protocol (recovered from `com.zhicase.petdoor` 1.1.1)

Source: APK `Pet Door 1.1.1` (APKPure), decompiled with jadx.
Authoritative classes:
- `com.zhicase.soundboxblecontrol_android.data.CMD_PET` — command builders (TX)
- `com.zhicase.soundboxblecontrol_android.ble.PetBleManagerAdapter` — UUIDs, connect sequence, response parser (RX)
- `com.zhicase.ble.base.BLEDeviceManager#sendData` — write path (verbatim, no wrapping)
- `com.zhicase.ble.base.BluetoothLeClass` — GATT plumbing, CCCD notify enable

The app is built on a generic `com.zhicase.ble` framework reused from a Bluetrum
soundbox app. The soundbox uses a different, checksummed `0xAB` protocol on
service `ff12`/`ffe0`. **Ignore the soundbox adapter (`BleManagerAdapter`) — the
door overrides everything below.**

## GATT

| Role | UUID | Notes |
|---|---|---|
| Service | `0000ff10-0000-1000-8000-00805f9b34fb` | `managerWithServiceUUIDPrefixString() = "0000ff10"` |
| Write   | `0000ff11-0000-1000-8000-00805f9b34fb` | `deviceUUID4CharacteristicWrite()` |
| Notify  | `0000ff12-0000-1000-8000-00805f9b34fb` | `deviceUUID4CharacteristicNotify()`, standard CCCD 0x2902, ENABLE_NOTIFICATION_VALUE (notify, not indicate) |

Write type is chosen at runtime from the characteristic's properties:
`WRITE_NO_RESPONSE (0x04)` present → write-without-response, else write-with-response.
Try without-response first. (The pending GATT dump will confirm ff11's props.)

MTU: the app does **not** request a custom MTU (`managerIsMTUEnable()=false`);
frames are ≤6 bytes so it never matters. The proxy negotiating 512 is fine.

## No authentication

There is **no** auth/pairing/handshake write. On connect the app only does
(`PetBleManagerAdapter.managerDidReadyWriteAndNotify`, after service discovery):

1. +500 ms: `5A 05 HH mm ss` (set device clock to phone local time, 24h)
2. +500 ms: `5A 00` (get params)
3. +3000 ms: `5A 00` (get params again)

The door's RTC/settings are volatile (reset on solar power loss — see manual), so
the integration should re-send the clock sync on every reconnect if timers are used.

## TX — commands (write to ff11)

Header byte = `0x5A` (90). Frame = `5A <cmd> [args…]`, sent **verbatim**.

| Command | Bytes (hex) | Builder |
|---|---|---|
| Get params / poll status | `5A 00` | `getCMD4GetParams()` |
| Open door | `5A 01` | `getCMD4SendOpenDoor()` |
| Close door | `5A 02` | `getCMD4SendCloseDoor()` |
| Set open-timer  | `5A 03 <on> <HH> <mm> <ss>` | `getCMD4SetOpenDoorTimer(on,h,m,s)` |
| Set close-timer | `5A 04 <on> <HH> <mm> <ss>` | `getCMD4SetCloseDoorTimer(on,h,m,s)` |
| Set clock | `5A 05 <HH> <mm> <ss>` | `getCMD4SetInitTime(h,m,s)` |
| Pause door | `5A 09` | `getCMD4SendPauseDoor()` |
| Light (lamp) on/off | `5A 0A <0|1>` | `getCMD4SendLightCtrl(z)` |
| Auto-open-by-light (light mode) on/off | `5A 0B <0|1>` | `getCMD4SendDoorAutoByLight(z)` |

`<on>` = 1 enable / 0 disable the timer. Times are raw bytes, 24-hour.

## RX — notifications (from ff12)

Header byte = `0x5B` (91). Parser ignores any frame whose first byte ≠ `0x5B`.
Frame = `5B <type> [payload…]`.

| Type | Bytes | Meaning |
|---|---|---|
| `01` | `5B 01` | door **opened** (`key_door_opened = 1`) |
| `02` | `5B 02` | door **closed** (`key_door_opened = 0`) |
| `03` | `5B 03 <on> <HH> <mm> <ss>` | open-timer settings |
| `04` | `5B 04 <on> <HH> <mm> <ss>` | close-timer settings |
| `06` | `5B 06 <opened> <oHH> <omm> <oss> <oOn> <cHH> <cmm> <css> <cOn> <autoByLight>` | **full status** (len ≥ 12), reply to `5A 00` |
| `0A` | `5B 0A` | auto-by-light enabled ack (`=1`) |
| `0B` | `5B 0B` | auto-by-light disabled ack (`=0`) |

Full-status `5B 06` byte map (index into the frame):
- [2] opened (0/1)
- [3][4][5] open-timer HH, mm, ss
- [6] open-timer on
- [7][8][9] close-timer HH, mm, ss
- [10] close-timer on
- [11] auto-by-light (light mode) on/off

Notes / gaps:
- State is **binary open/closed only** — no position %, no explicit "moving" or
  "paused" state is reported. HA cover should be open/closed/opening/closing with
  opening/closing inferred from the last command until the next `5B 01`/`02`.
- The **lamp** on/off state (`5A 0A`) is *not* reflected in any RX frame; only the
  auto-by-light flag is. Don't expect readback for the lamp.

## Poll cycle for the HA integration (matches the "poll, don't hold" decision)

1. Connect (no bond). 2. Enable notify on `ff12`. 3. (optional) `5A 05 HH mm ss`.
4. Write `5A 00`. 5. Read the `5B 06` notification → parse status. 6. Disconnect.

## Probe test commands (needs HA's config entry disabled — see handoff BLOCKER)

```bash
W=0000ff11-0000-1000-8000-00805f9b34fb
N=0000ff12-0000-1000-8000-00805f9b34fb
# poll status
python ble_proxy_probe.py write --host 10.20.40.158 --password '<psk>' \
  --mac 41:42:F8:E0:55:59 --char $W --data 5a00 --listen $N
# open / close / pause
#   --data 5a01   |   --data 5a02   |   --data 5a09
```
