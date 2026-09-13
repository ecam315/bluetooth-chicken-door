"""Constants for the BF821 coop door integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "bf821_door"

# GATT (recovered from com.zhicase.petdoor 1.1.1 -- see apk-re/PROTOCOL.md)
SERVICE_UUID: Final = "0000ff10-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ff11-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ff12-0000-1000-8000-00805f9b34fb"

# CONF_ADDRESS comes from homeassistant.const; only our own keys live here.
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

# The door is solar powered; a held link costs meaningfully more than
# advertising, so we connect only to poll and then drop the link.
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 5
MIN_SCAN_INTERVAL_MINUTES: Final = 1
MAX_SCAN_INTERVAL_MINUTES: Final = 60

# Seconds to wait for the first status frame after asking for it.
STATUS_TIMEOUT: Final = 10.0
# A poll is answered with a burst of separate frames rather than one combined
# frame, so the reply is considered complete once this long passes with no
# further notification. Observed spacing between frames is ~30-80 ms.
STATUS_SETTLE: Final = 1.2
# Gap between consecutive writes in one session; the firmware drops frames
# that arrive back to back.
WRITE_GAP: Final = 0.2
# How long after a move command we report opening/closing before trusting
# the polled state again. Normal travel is well under this; the ~3 min
# self-calibration sweep is not covered on purpose.
MOTION_TIMEOUT: Final = 60.0
# Delay before the confirmation poll that follows a command.
POST_COMMAND_REFRESH: Final = 30.0
