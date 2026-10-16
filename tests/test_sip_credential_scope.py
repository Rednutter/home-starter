"""The SIP HTTP response must not expose another HA account's credentials."""

import ast
import copy

import pytest
from sip_core_credential_scope import SCOPE, repair


def merge(base, overrides):
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value


def test_only_exact_ha_id_receives_own_credentials_without_shared_fallback():
    namespace = {"copy": copy, "deep_update": merge}
    exec(compile(ast.parse(SCOPE), "<scope>", "exec"), namespace)  # noqa: S102 -- checked repository source, no external input
    source = {
        "users": [
            {
                "ha_username": "a",
                "extension": "201",
                "password": "secret-a",  # pragma: allowlist secret -- synthetic isolation fixture
                "overrides": {"users": [{"password": "injected"}], "auto_open": True},  # pragma: allowlist secret -- synthetic override fixture
            },
            {"ha_username": "b", "extension": "202", "password": "secret-b"},  # pragma: allowlist secret -- synthetic isolation fixture
        ],
        "backup_user": {"password": "shared"},  # pragma: allowlist secret -- synthetic isolation fixture
        "popup_config": {"extensions": {"201": {"name": "Example"}}},
    }
    original = copy.deepcopy(source)
    own = namespace["scoped_sip_config"](source, "a")
    assert len(own["users"]) == 1 and own["users"][0]["password"] == "secret-a"  # pragma: allowlist secret -- synthetic isolation assertion
    assert "secret-b" not in str(own) and "injected" not in str(own) and "backup_user" not in own
    assert own["auto_open"] is True
    unknown = namespace["scoped_sip_config"](source, "unknown")
    assert unknown["users"] == [] and "backup_user" not in unknown
    assert source == original


def test_repair_refuses_unknown_or_already_patched_implementation():
    source = """class SipCoreConfigView(HomeAssistantView):
    async def get(self, request: Request):
        user = request["hass_user"]
        name = user.name
        return self.json(sip_config)
"""
    result = repair(source)
    assert 'request["hass_user"].id' in result and "name = user.name" not in result
    with pytest.raises(ValueError, match="already present"):
        repair(result)
