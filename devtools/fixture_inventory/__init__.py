from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr


async def async_setup_entry(hass, entry):
    areas = ar.async_get(hass)
    kitchen = areas.async_get_area_by_name("Kitchen") or areas.async_create("Kitchen")
    registry = dr.async_get(hass)
    first = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("fixture_inventory", "kitchen")},
        manufacturer="Fixture maker",
        model="Fixture device",
        name="Kitchen temperature",
    )
    registry.async_update_device(first.id, area_id=kitchen.id)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("fixture_inventory", "garage")},
        manufacturer="Fixture maker",
        model="Fixture device",
        name="Garage battery",
    )
    registry.async_get_or_create_child(
        config_entry_id=entry.entry_id, parent_device_id=first.id, identifiers={("fixture_inventory", "zone_one")}, name="Fixture zone one"
    )
    registry.async_get_or_create_child(
        config_entry_id=entry.entry_id, parent_device_id=first.id, identifiers={("fixture_inventory", "zone_two")}, name="Fixture zone two"
    )
    return True
