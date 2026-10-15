"""Constants for Jarolift RF."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "jarolift_rf"

CONF_BRIDGE_SERVICE: Final = "bridge_service"
CONF_MASTER_MSB: Final = "master_msb"
CONF_MASTER_LSB: Final = "master_lsb"
CONF_BASE_SERIAL: Final = "base_serial"
CONF_COUNTER_START: Final = "counter_start"
CONF_CONFIG_JSON: Final = "config_json"
CONF_CHANNEL_NAMES: Final = "channel_names"

OPT_TX_ENABLED: Final = "tx_enabled"
OPT_TX_POWER: Final = "tx_power_dbm"
OPT_BUNDLE_MS: Final = "bundle_ms"
OPT_LEGACY_LEARN: Final = "legacy_learn"

DEFAULT_TX_POWER: Final = 0  # the v1.9.0 controller effectively sent with PATABLE 0x60 (~0 dBm)
DEFAULT_BUNDLE_MS: Final = 100

SUBENTRY_CHANNEL: Final = "channel"
SUBENTRY_GROUP: Final = "group"
CONF_CHANNEL: Final = "channel"  # 1-based, as in the original WebUI
CONF_CHANNELS: Final = "channels"

BRIDGE_ACTION_SUFFIX: Final = "_send_raw"
ESPHOME_DOMAIN: Final = "esphome"

COMMAND_MAX_AGE_S: Final = 10.0
COUNTER_WARN_AT: Final = 65000

SIGNAL_STATE: Final = f"{DOMAIN}_state_{{}}"  # format with entry_id
SIGNAL_COUNTER: Final = f"{DOMAIN}_counter_{{}}"
