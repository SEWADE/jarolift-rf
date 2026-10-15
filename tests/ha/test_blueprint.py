from pathlib import Path

from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

BLUEPRINT = Path(__file__).parents[2] / "blueprints/automation/jarolift_rf/timer.yaml"


async def test_timer_blueprint_is_valid(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "automation", {})
    data = load_yaml(BLUEPRINT)
    blueprint = models.Blueprint(data, expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    inputs = models.BlueprintInputs(
        blueprint,
        {"use_blueprint": {"path": "jarolift_rf/timer.yaml", "input": {
            "shutters": ["cover.jarolift_a"], "command": "close", "mode": "sunset",
            "offset": "-00:30:00", "use_max": True, "max_time": "21:00:00"}}},
    )
    config = inputs.async_substitute()
    config["id"] = "test"
    assert await async_validate_config_item(hass, "automation.test", config) is not None
