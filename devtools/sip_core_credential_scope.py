"""Narrow compatibility repair for the inspected SIP Core HTTP view.

Apply only to the matching upstream implementation, after a private backup.
HA must restart to load the changed Python module. HACS updates may replace it.
"""

import ast

SCOPE = '''def scoped_sip_config(source, user_id):
    """Return only the authenticated HA user's explicitly bound SIP identity."""
    config = copy.deepcopy(source)
    matched = next((u for u in config.get("users", []) if u.get("ha_username") == user_id), None)
    if matched and isinstance(matched.get("overrides"), dict):
        deep_update(config, matched["overrides"])
    config.pop("backup_user", None)
    config["users"] = [{k: v for k, v in matched.items() if k != "overrides"}] if matched else []
    return config


'''


def repair(source):
    if "def scoped_sip_config(" in source:
        raise ValueError("Credential scope repair is already present; review rather than overwrite.")
    tree = ast.parse(source)
    view = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SipCoreConfigView")
    method = next(n for n in view.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get")
    original = ast.get_source_segment(source, method)
    if not original or "return self.json(sip_config)" not in original or "user.name" not in original:
        raise ValueError("SIP Core implementation changed; inspect it before applying this repair.")
    replacement = '''async def get(self, request: Request):
        """Return credential-scoped configuration for the signed-in HA user."""
        hass: HomeAssistant = request.app["hass"]
        try:
            config = scoped_sip_config(hass.data[DOMAIN]["options"]["sip_config"], request["hass_user"].id)
            return self.json(config)
        except (KeyError, TypeError, AttributeError):
            return self.json({"error": "No valid SIP configuration found"}, status_code=503)'''
    result = source.replace(original, replacement, 1)
    result = result.replace("class SipCoreConfigView(", SCOPE + "class SipCoreConfigView(", 1)
    for line in ["    logger.info(config_entry.data)\n", "    logger.info(config_entry.options)\n"]:
        result = result.replace(line, "")
    ast.parse(result)
    return result
