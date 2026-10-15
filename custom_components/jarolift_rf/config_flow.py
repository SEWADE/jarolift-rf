"""Config flow: bridge, keys, serial, counter; channels and groups as subentries."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .bridge import find_esphome_bridges
from .const import (
    CONF_BASE_SERIAL,
    CONF_BRIDGE_SERVICE,
    CONF_CHANNEL,
    CONF_CHANNEL_NAMES,
    CONF_CHANNELS,
    CONF_CONFIG_JSON,
    CONF_COUNTER_START,
    CONF_MASTER_LSB,
    CONF_MASTER_MSB,
    CONF_REMOTE_SERIAL,
    DEFAULT_BUNDLE_MS,
    DEFAULT_TX_POWER,
    DOMAIN,
    OPT_BUNDLE_MS,
    OPT_LEGACY_LEARN,
    OPT_TX_ENABLED,
    OPT_TX_POWER,
    SUBENTRY_CHANNEL,
    SUBENTRY_GROUP,
    SUBENTRY_REMOTE,
)
from .core.telegram import MAX_BASE_SERIAL, NUM_CHANNELS
from .counter import MAX_COUNTER, MIN_COUNTER

CHANNEL_OPTIONS = [str(n) for n in range(1, NUM_CHANNELS + 1)]


def parse_int(value: Any, maximum: int) -> int:
    """Decimal, or hex with 0x prefix (as shown in the original WebUI/config.json)."""
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip().lower()
        number = int(text, 16) if text.startswith("0x") else int(text)
    if not 0 <= number <= maximum:
        raise ValueError
    return number


def serial_unique_id(base_serial: int) -> str:
    return hashlib.sha256(f"{DOMAIN}:{base_serial}".encode()).hexdigest()[:16]


def parse_original_config(text: str) -> dict[str, Any]:
    """Read keys, serial, channels and groups from the original controller's config.json."""
    jaro = json.loads(text)["jaro"]
    names = [str(n).strip() for n in jaro.get("ch_name", [])]
    channels = [
        (i + 1, names[i])
        for i, enabled in enumerate(jaro.get("ch_enable", []))
        if enabled and i < NUM_CHANNELS and names[i]
    ]
    groups: list[tuple[str, list[int], bool]] = []
    for i, enabled in enumerate(jaro.get("grp_enable", [])):
        name = str(jaro["grp_name"][i]).strip()
        if not enabled or not name:
            continue
        mask = int(jaro["grp_mask"][i])
        members = [n for n in range(1, NUM_CHANNELS + 1) if mask & (1 << (n - 1))]
        derived = False
        if not members:
            # Mask 0 addresses no motor. If the channel names follow "<group> - <name>",
            # suggest those channels; the user confirms in the import summary.
            members = [n for n, cname in channels if cname.lower().startswith(name.lower())]
            derived = True
        if members:
            groups.append((name, members, derived))
    remotes: list[tuple[str, int, list[int]]] = []
    for i, enabled in enumerate(jaro.get("remote_enable", [])):
        name = str(jaro["remote_name"][i]).strip()
        serial = int(jaro["remote_serial"][i])
        if enabled and name and serial:
            mask = int(jaro["remote_mask"][i])
            remotes.append((name, serial, [n for n in range(1, NUM_CHANNELS + 1) if mask & (1 << (n - 1))]))
    return {
        "remotes": remotes,
        CONF_MASTER_MSB: jaro.get("masterMSB"),
        CONF_MASTER_LSB: jaro.get("masterLSB"),
        CONF_BASE_SERIAL: jaro.get("serial"),
        "channels": channels,
        "groups": groups,
    }


def parse_channel_lines(text: str) -> list[tuple[int, str]]:
    """One shutter name per line -> channels 1..n (empty lines skip a channel number)."""
    lines = text.splitlines() if text.strip() else []
    return [(i + 1, line.strip()) for i, line in enumerate(lines[:NUM_CHANNELS]) if line.strip()]


class JaroliftConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._subentries: list[ConfigSubentryData] = []
        self._derived: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JaroliftOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_CHANNEL: ChannelSubentryFlow,
            SUBENTRY_GROUP: GroupSubentryFlow,
            SUBENTRY_REMOTE: RemoteSubentryFlow,
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not find_esphome_bridges(self.hass):
            return self.async_abort(reason="no_bridge")
        return self.async_show_menu(step_id="user", menu_options=["manual", "import_config"])

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """New installation: keys by hand, serial by hand or generated, channels optional."""
        return await self._async_step_setup("manual", user_input)

    async def async_step_import_config(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Take over an existing ESP32-Jarolift-Controller via its config.json."""
        return await self._async_step_setup("import_config", user_input)

    async def _async_step_setup(self, step_id: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        bridges = find_esphome_bridges(self.hass)
        if not bridges:
            return self.async_abort(reason="no_bridge")
        errors: dict[str, str] = {}
        if user_input is not None:
            imported: dict[str, Any] = {}
            if step_id == "import_config":
                try:
                    imported = parse_original_config(user_input.get(CONF_CONFIG_JSON, ""))
                except (ValueError, KeyError, TypeError, IndexError):
                    errors[CONF_CONFIG_JSON] = "invalid_config_json"
            else:
                imported = {"channels": parse_channel_lines(user_input.get(CONF_CHANNEL_NAMES, ""))}
            values: dict[str, int] = {}
            for key, maximum in (
                (CONF_MASTER_MSB, 0xFFFFFFFF),
                (CONF_MASTER_LSB, 0xFFFFFFFF),
                (CONF_BASE_SERIAL, MAX_BASE_SERIAL),
            ):
                raw = user_input.get(key) or imported.get(key)
                if raw in (None, ""):
                    if key == CONF_BASE_SERIAL and step_id == "manual":
                        values[key] = secrets.randbelow(MAX_BASE_SERIAL) + 1  # new installation
                        continue
                    errors.setdefault(key, "required")
                    continue
                try:
                    values[key] = parse_int(raw, maximum)
                except ValueError:
                    errors[key] = "invalid_serial" if key == CONF_BASE_SERIAL else "invalid_key"
            if values.get(CONF_MASTER_MSB) == 0 and values.get(CONF_MASTER_LSB) == 0:
                errors[CONF_MASTER_MSB] = "invalid_key"
            if not errors:
                await self.async_set_unique_id(serial_unique_id(values[CONF_BASE_SERIAL]))
                self._abort_if_unique_id_configured()
                self._data = {
                    CONF_BRIDGE_SERVICE: user_input[CONF_BRIDGE_SERVICE],
                    **values,
                    CONF_COUNTER_START: int(user_input[CONF_COUNTER_START]),
                }
                self._options = {
                    OPT_TX_ENABLED: user_input.get(OPT_TX_ENABLED, False),
                    OPT_TX_POWER: DEFAULT_TX_POWER,
                    OPT_BUNDLE_MS: DEFAULT_BUNDLE_MS,
                    OPT_LEGACY_LEARN: user_input.get(OPT_LEGACY_LEARN, False),
                }
                self._build_import(imported)
                if step_id == "import_config":
                    return await self.async_step_import_summary()
                return self._create()

        fields: dict[Any, Any] = {
            vol.Required(CONF_BRIDGE_SERVICE, default=bridges[0]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=bridges, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
        }
        if step_id == "import_config":
            fields[vol.Required(CONF_CONFIG_JSON)] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            fields[vol.Optional(CONF_MASTER_MSB)] = _secret_text()
            fields[vol.Optional(CONF_MASTER_LSB)] = _secret_text()
            fields[vol.Optional(CONF_BASE_SERIAL)] = _secret_text()
        else:
            fields[vol.Required(CONF_MASTER_MSB)] = _secret_text()
            fields[vol.Required(CONF_MASTER_LSB)] = _secret_text()
            fields[vol.Optional(CONF_BASE_SERIAL)] = _secret_text()
            fields[vol.Optional(CONF_CHANNEL_NAMES)] = selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            )
        fields[vol.Required(CONF_COUNTER_START, default=MIN_COUNTER)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=MIN_COUNTER, max=MAX_COUNTER, step=1, mode=selector.NumberSelectorMode.BOX)
        )
        fields[vol.Optional(OPT_LEGACY_LEARN, default=False)] = selector.BooleanSelector()
        fields[vol.Optional(OPT_TX_ENABLED, default=False)] = selector.BooleanSelector()
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(fields), errors=errors)

    def _build_import(self, imported: dict[str, Any]) -> None:
        self._subentries = [
            ConfigSubentryData(
                subentry_type=SUBENTRY_CHANNEL, title=name, data={CONF_CHANNEL: ch}, unique_id=f"channel_{ch}"
            )
            for ch, name in imported.get("channels", [])
        ]
        for name, members, derived in imported.get("groups", []):
            self._subentries.append(
                ConfigSubentryData(
                    subentry_type=SUBENTRY_GROUP, title=name, data={CONF_CHANNELS: members}, unique_id=None
                )
            )
            if derived:
                self._derived.append(f"{name}: {', '.join(map(str, members))}")
        for name, serial, members in imported.get("remotes", []):
            self._subentries.append(
                ConfigSubentryData(
                    subentry_type=SUBENTRY_REMOTE, title=name,
                    data={CONF_REMOTE_SERIAL: serial, CONF_CHANNELS: members}, unique_id=f"remote_{serial}",
                )
            )

    async def async_step_import_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._create()
        channels = [s for s in self._subentries if s["subentry_type"] == SUBENTRY_CHANNEL]
        groups = [s for s in self._subentries if s["subentry_type"] == SUBENTRY_GROUP]
        remotes = [s for s in self._subentries if s["subentry_type"] == SUBENTRY_REMOTE]
        return self.async_show_form(
            step_id="import_summary",
            data_schema=vol.Schema({}),
            description_placeholders={
                "channels": "\n".join(f"- {s['data'][CONF_CHANNEL]}: {s['title']}" for s in channels) or "-",
                "groups": "\n".join(
                    f"- {s['title']}: {', '.join(map(str, s['data'][CONF_CHANNELS]))}" for s in groups
                )
                or "-",
                "derived": "\n".join(f"- {d}" for d in self._derived) or "-",
                "remotes": "\n".join(f"- {s['title']}" for s in remotes) or "-",
            },
        )

    def _create(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title="Jarolift", data=self._data, options=self._options, subentries=self._subentries
        )


def _secret_text() -> selector.TextSelector:
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


class JaroliftOptionsFlow(OptionsFlow):
    """Plain OptionsFlow: the entry's update listener reloads (also needed for subentry changes)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[OPT_TX_POWER] = int(user_input[OPT_TX_POWER])
            user_input[OPT_BUNDLE_MS] = int(user_input[OPT_BUNDLE_MS])
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(OPT_TX_ENABLED, default=opts.get(OPT_TX_ENABLED, False)): selector.BooleanSelector(),
                vol.Required(OPT_TX_POWER, default=opts.get(OPT_TX_POWER, DEFAULT_TX_POWER)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=-30, max=10, step=1, unit_of_measurement="dBm")
                ),
                vol.Required(OPT_BUNDLE_MS, default=opts.get(OPT_BUNDLE_MS, DEFAULT_BUNDLE_MS)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=500, step=10, unit_of_measurement="ms")
                ),
                vol.Required(OPT_LEGACY_LEARN, default=opts.get(OPT_LEGACY_LEARN, False)): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _used_channels(entry: ConfigEntry, exclude: str | None = None) -> set[int]:
    return {
        s.data[CONF_CHANNEL]
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_CHANNEL and s.subentry_id != exclude
    }


class ChannelSubentryFlow(ConfigSubentryFlow):
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        free = [c for c in CHANNEL_OPTIONS if int(c) not in _used_channels(entry)]
        if not free:
            return self.async_abort(reason="no_free_channel")
        if user_input is not None:
            ch = int(user_input[CONF_CHANNEL])
            return self.async_create_entry(
                title=user_input[CONF_NAME].strip(), data={CONF_CHANNEL: ch}, unique_id=f"channel_{ch}"
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_CHANNEL, default=free[0]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=free, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(self._get_entry(), subentry, title=user_input[CONF_NAME].strip())
        schema = vol.Schema({vol.Required(CONF_NAME, default=subentry.title): selector.TextSelector()})
        return self.async_show_form(step_id="reconfigure", data_schema=schema)


def _channel_options(entry: ConfigEntry) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=str(s.data[CONF_CHANNEL]), label=f"{s.data[CONF_CHANNEL]}: {s.title}")
        for s in sorted(entry.subentries.values(), key=lambda s: s.data.get(CONF_CHANNEL, 0))
        if s.subentry_type == SUBENTRY_CHANNEL
    ]


class GroupSubentryFlow(ConfigSubentryFlow):
    def _schema(self, name: str = "", members: list[str] | None = None) -> vol.Schema:
        options = _channel_options(self._get_entry())
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=name): selector.TextSelector(),
                vol.Required(CONF_CHANNELS, default=members or []): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                ),
            }
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CHANNELS]:
                errors[CONF_CHANNELS] = "no_channels"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME].strip(),
                    data={CONF_CHANNELS: sorted(int(c) for c in user_input[CONF_CHANNELS])},
                )
        return self.async_show_form(step_id="user", data_schema=self._schema(), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CHANNELS]:
                errors[CONF_CHANNELS] = "no_channels"
            else:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=user_input[CONF_NAME].strip(),
                    data={CONF_CHANNELS: sorted(int(c) for c in user_input[CONF_CHANNELS])},
                )
        members = [str(c) for c in subentry.data[CONF_CHANNELS]]
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(subentry.title, members), errors=errors
        )


MANUAL = "manual"


class RemoteSubentryFlow(ConfigSubentryFlow):
    """Original remote: pick a recently received unknown remote, or enter its serial."""

    def _schema(self, name: str = "", members: list[str] | None = None, *, with_source: bool) -> vol.Schema:
        fields: dict[Any, Any] = {vol.Required(CONF_NAME, default=name): selector.TextSelector()}
        if with_source:
            receiver = getattr(self._get_entry().runtime_data, "receiver", None)
            seen = list(receiver.recent_unknown.values())[::-1] if receiver else []
            options = [
                selector.SelectOptionDict(
                    value=str(r.remote_serial),
                    label=f"{time.strftime('%H:%M:%S', time.localtime(time.time() - (time.monotonic() - r.seen)))}"
                    f" · {r.event_type} · mask 0x{r.channel_mask:04X}{' ✓' if r.verified else ''}",
                )
                for r in seen
            ] + [selector.SelectOptionDict(value=MANUAL, label="manual")]
            fields[vol.Required("source", default=options[0]["value"])] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, translation_key="remote_source")
            )
            fields[vol.Optional(CONF_REMOTE_SERIAL)] = selector.TextSelector()
        fields[vol.Optional(CONF_CHANNELS, default=members or [])] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=_channel_options(self._get_entry()), multiple=True)
        )
        return vol.Schema(fields)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                if user_input["source"] == MANUAL:
                    serial = parse_int(user_input.get(CONF_REMOTE_SERIAL, ""), MAX_BASE_SERIAL)
                else:
                    serial = int(user_input["source"])
            except ValueError:
                errors[CONF_REMOTE_SERIAL] = "invalid_serial"
            else:
                if any(
                    s.subentry_type == SUBENTRY_REMOTE and s.data[CONF_REMOTE_SERIAL] == serial
                    for s in self._get_entry().subentries.values()
                ):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=user_input[CONF_NAME].strip(),
                    data={CONF_REMOTE_SERIAL: serial,
                          CONF_CHANNELS: sorted(int(c) for c in user_input.get(CONF_CHANNELS, []))},
                    unique_id=f"remote_{serial}",
                )
        return self.async_show_form(step_id="user", data_schema=self._schema(with_source=True), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input[CONF_NAME].strip(),
                data_updates={CONF_CHANNELS: sorted(int(c) for c in user_input.get(CONF_CHANNELS, []))},
            )
        members = [str(c) for c in subentry.data.get(CONF_CHANNELS, [])]
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(subentry.title, members, with_source=False)
        )
