"""Prepare a disposable view-only dashboard locally. Never publishes or authenticates."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .surfaces import fingerprint

PREVIEW_PATH = "home-starter-airtouch-preview"
_GUARD = Path(__file__).parent / "static" / "panel-preview-guard.js"
_NATIVE = """const s=hass.states[variables.preview_entity],a=s?.attributes || {};
const known=s && !['unknown','unavailable'].includes(s.state);
const esc=v=>String(v ?? '').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));
const reading=known && typeof a.current_temperature==='number' && Number.isFinite(a.current_temperature) ? ' · '+a.current_temperature+'°':'';
const content='<h3>'+esc(variables.preview_name)+'</h3><p>'+esc(known ? s.state:'Unavailable')+esc(reading)+'</p>';
return html`<section .innerHTML=${content+'<p>Native controls disabled in preview</p>'}></section>`;"""


def prepare(config: dict, source_path: str, *, preview_path: str = PREVIEW_PATH) -> dict:
    """Return config + review manifest. Unknown cards become inert state summaries.

    Keep original surface/person/epoch scope and context entities; this is not a
    new managed household surface and must not be added to publication records.
    """
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", preview_path) or preview_path == source_path:
        raise ValueError("Use a distinct non-default preview address.")
    if not isinstance(config.get("views"), list) or not config["views"]:
        raise ValueError("A reviewed generated dashboard is required.")
    if any(v.get("type") != "panel" for v in config["views"]):
        raise ValueError("Only reviewed landscape panel views are supported.")
    paths = [v.get("path") for v in config["views"]]
    if any(not isinstance(p, str) or not re.fullmatch(r"[a-z0-9_-]+", p) for p in paths) or len(paths) != len(set(paths)):
        raise ValueError("Every preview view needs a unique local route.")
    base, original = "/" + preview_path, "/" + source_path
    allowed = [base + "/" + p for p in paths]
    guard = _GUARD.read_text(encoding="utf-8").replace("PREVIEW_PATHS", json.dumps(allowed))
    wrapped, native = 0, 0

    def script(value):
        nonlocal wrapped
        match = re.fullmatch(r"(\[{3,})\s*(.*?)\s*(\]{3,})", value, re.DOTALL)
        if not match:
            return value
        if len(match[1]) != len(match[3]):
            raise ValueError("Unrecognised template nesting; preserve the original dashboard.")
        wrapped += 1
        return (
            match[1]
            + "\n"
            + guard
            + "\nconst previewResult=(function(hass,variables,html,helpers,fetch){\n"
            + match[2]
            + "\n}).call(this,previewHass,previewVariables,previewHTML,previewHelpers,previewDenied);"
            + "\nreturn typeof previewResult==='string' ? previewMarkup(previewResult):previewResult;\n"
            + match[3]
        )

    def walk(value):
        nonlocal native
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            if value == original:
                return base
            if value.startswith(original + "/"):
                return base + value[len(original) :]
            if value.startswith("{"):
                try:
                    return json.dumps(walk(json.loads(value)))
                except json.JSONDecodeError:
                    pass
            # No remote or camera CSS fetches; approved embedded artwork only.
            value = re.sub(r"url\(\s*(?![\"']?data:image/)[^)]*\)", "none", value, flags=re.I)
            return script(value)
        if not isinstance(value, dict):
            return value
        kind = value.get("type")
        if kind and kind not in {"panel", "custom:button-card"}:
            native += 1
            return walk(
                {
                    "type": "custom:button-card",
                    "show_name": False,
                    "show_icon": False,
                    "variables": {"preview_entity": value.get("entity"), "preview_name": value.get("name", "Selected control")},
                    "custom_fields": {"state": "[[[" + _NATIVE + "]]]"},
                    "tap_action": {"action": "none"},
                }
            )
        result = {}
        for key, child in value.items():
            if key.endswith("_action"):
                result[key] = (
                    {"action": "navigate", "navigation_path": base + child["navigation_path"][len(original) :]}
                    if isinstance(child, dict)
                    and child.get("action") == "navigate"
                    and child.get("navigation_path", "").startswith(original + "/")
                    and base + child["navigation_path"][len(original) :] in allowed
                    else {"action": "none"}
                )
            elif key not in {"features", "camera_image", "image", "picture", "entity_picture"}:
                result[key] = walk(child)
        if kind == "custom:button-card":
            result.update(tap_action={"action": "none"}, hold_action={"action": "none"}, double_tap_action={"action": "none"})
            result["show_entity_picture"] = False
            result.pop("entity", None)  # No implicit more-info or native entity consumer.
        return result

    preview = walk(copy.deepcopy(config))
    preview["title"] = "AirTouch · view-only preview"
    preview.pop("kiosk_mode", None)  # Keep an operator escape; do not configure kiosk defaults.
    if not wrapped:
        raise ValueError("No generated templates found; refuse an unguarded preview.")
    return {
        "url_path": preview_path,
        "show_in_sidebar": False,
        "config": preview,
        "fingerprint": fingerprint(preview),
        "source_fingerprint": fingerprint(config),
        "review": {
            "wrapped_templates": wrapped,
            "native_replacements": native,
            "routes": allowed,
            "controls": "disabled",
            "network": "existing HA state subscription only; no media/camera requests",
        },
    }


def verify(prepared: dict, source: dict, source_path: str) -> None:
    """Reject tampered/stale preparations before any separately authorised write."""
    expected = prepare(source, source_path, preview_path=prepared.get("url_path", ""))
    if prepared != expected:
        raise ValueError("Preview differs from the reviewed source/guard; regenerate and review.")
