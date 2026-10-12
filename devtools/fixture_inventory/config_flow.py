from homeassistant.config_entries import ConfigFlow


class Flow(ConfigFlow, domain="fixture_inventory"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_create_entry(title="Fixture devices", data={})
