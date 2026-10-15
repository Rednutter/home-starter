"""Physical display commissioning. Native users own auth; evidence never contains secrets."""

import re
import secrets
from datetime import UTC, datetime, timedelta

from .context import safe
from .core import CoreError
from .household import ID, text
from .surfaces import fingerprint, publish
from .this_house import digest
from .this_house import load as house_confirmations

PERMISSIONS = {"control": "Non-admin household controls", "read_only": "Read-only"}


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Display evidence needs an aware timestamp.")
    return result.astimezone(UTC)


def required(surface):
    return surface["profile"] != "phone"


def signature(surface):
    return fingerprint(surface)


def path_for(surface):
    return "home-starter-" + surface["id"].replace("_", "-")


def empty(house):
    return {"version": 1, "epoch": house["epoch"], "revision": 0, "screens": {}}


def load(store, house):
    value = store.read(store.screen_identity_path, None)
    if value is None:
        return empty(house)
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "epoch", "revision", "screens"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or any(type(value[k]) is not int or value[k] < 0 for k in ("epoch", "revision"))
        or not isinstance(value["screens"], dict)
        or len(value["screens"]) > 50
    ):
        raise ValueError("Unsupported display commissioning data. Existing files are preserved.")
    for key, row in value["screens"].items():
        if (
            not ID.fullmatch(key)
            or not isinstance(row, dict)
            or set(row)
            != {
                "user_id",
                "permission",
                "user_signature",
                "surface_signature",
                "dashboard_fingerprint",
                "helper",
                "page",
                "attempt",
                "session",
                "restart",
                "physical",
                "prepared",
            }
        ):
            raise ValueError("Invalid display commissioning record.")
        if not text(row["user_id"], 64) or row["permission"] not in PERMISSIONS:
            raise ValueError("Invalid display account choice.")
        if any(
            not isinstance(row[k], str) or not re.fullmatch("[a-f0-9]{64}", row[k]) for k in ("user_signature", "surface_signature", "dashboard_fingerprint")
        ):
            raise ValueError("Invalid display evidence identity.")
        for field, keys in {
            "helper": {"id", "entity_id", "name"},
            "page": {"url_path", "fingerprint"},
            "attempt": {"at", "stage", "baseline"},
            "session": {"at", "context_id", "user_id"},
            "restart": {"at", "context_id", "user_id"},
            "physical": {"at", "by", "restart_kind"},
            "prepared": {"at", "by", "change"},
        }.items():
            item = row[field]
            if item is not None and (not isinstance(item, dict) or set(item) != keys or any(v is not None and not text(v, 200) for v in item.values())):
                raise ValueError("Invalid display verification history.")
            if item and "at" in item:
                stamp(item["at"])
        if row["attempt"] and row["attempt"]["stage"] not in {"session", "restart"}:
            raise ValueError("Invalid display check stage.")
        if row["physical"] and row["physical"]["restart_kind"] not in {"browser", "app", "device"}:
            raise ValueError("Invalid physical restart report.")
    # Reset revokes the old binding, without deleting native accounts or resources.
    if value["epoch"] > house["epoch"]:
        raise ValueError("Display history belongs to a newer household epoch. Restore matching data before changing it.")
    return value if value["epoch"] == house["epoch"] else empty(house)


def save(store, value):
    value["revision"] += 1
    store.write(store.screen_identity_path, value)


async def accounts(core, store=None):
    async with core.websocket() as ws:
        users = await ws.command("config/auth/list")
        people = await ws.command("person/list")
    if not isinstance(users, list) or not isinstance(people, dict) or any(not isinstance(people.get(k), list) for k in ("storage", "config")):
        raise CoreError("api", "Display accounts and Person links could not be inspected.")
    linked = {p.get("user_id") for k in ("storage", "config") for p in people[k]}
    try:
        reviewed = house_confirmations(store)["people"] if store else {}
    except (ValueError, OSError, KeyError, TypeError):
        reviewed = {}
    display_links = set()
    for source in ("storage", "config"):
        for person in people[source]:
            decision = reviewed.get(person.get("id"), {})
            if (
                decision.get("role") == "other"
                and not person.get("device_trackers")
                and decision.get("signature") == digest([person["id"], person["name"], sorted(person.get("device_trackers", []))])
            ):
                display_links.add(person.get("user_id"))
    display_links = {u for u in display_links if sum(p.get("user_id") == u for source in ("storage", "config") for p in people[source]) == 1}
    result = []
    for user in users:
        if not isinstance(user, dict) or not text(user.get("id"), 64) or not isinstance(user.get("group_ids"), list):
            raise CoreError("api", "Unexpected HA user response.")
        groups = set(user["group_ids"])
        reason = (
            "Owner, administrator or system account"
            if user.get("is_owner") or user.get("system_generated") or "system-admin" in groups
            else "Linked to a HA Person"
            if user["id"] in linked - display_links
            else "Inactive account"
            if user.get("is_active") is not True
            else "Enable local-only access in HA"
            if user.get("local_only") is not True
            else "Finish the native HA login credentials"
            if not user.get("username") or not any(c.get("type") == "homeassistant" for c in user.get("credentials", []))
            else "Unsupported permission group"
            if groups not in ({"system-users"}, {"system-read-only"})
            else None
        )
        permission = "read_only" if groups == {"system-read-only"} else "control"
        result.append(
            {
                "id": user["id"],
                "name": user.get("name") or "Unnamed HA user",
                "username": user.get("username"),
                "permission": permission,
                "issue": reason,
                "signature": fingerprint(user),
                "can_prepare": (
                    reason == "Enable local-only access in HA"
                    and groups in ({"system-users"}, {"system-read-only"})
                    and bool(user.get("username"))
                    and any(c.get("type") == "homeassistant" for c in user.get("credentials", []))
                ),
            }
        )
    return result


def current(surface, row, publication, users):
    if not publication or publication["status"] != "published":
        return "Publish and read back the intended dashboard first."
    if not row:
        return "Dashboard ready — display identity not yet verified."
    user = next((u for u in users if u["id"] == row["user_id"]), None)
    if not user or user["issue"] or user["permission"] != row["permission"]:
        return "The intended dedicated account is missing or unsuitable."
    if (
        user["signature"] != row["user_signature"]
        or signature(surface) != row["surface_signature"]
        or publication["fingerprint"] != row["dashboard_fingerprint"]
    ):
        return "Account, screen or dashboard changed; review and verify again."
    return None


async def inspect(core, store, house, publications):
    try:
        value, storage_issue = load(store, house), None
    except (ValueError, OSError, KeyError, TypeError):
        value, storage_issue = empty(house), "Display commissioning history cannot be read safely. Saved data is preserved; repair it before making changes."
    try:
        users, issue = await accounts(core, store), None
    except CoreError:
        users, issue = [], "HA account inspection unavailable; existing evidence is preserved."
    rows = []
    for surface in house["surfaces"]:
        row = value["screens"].get(surface["id"])
        publication = next((s for s in publications if s["id"] == surface["id"]), None)
        problem = storage_issue or issue or current(surface, row, publication, users)
        stage = (
            "commissioned"
            if not problem and row["physical"] and row["session"] and row["restart"]
            else "authenticated"
            if not problem and row["session"]
            else "published"
            if publication and publication["status"] == "published"
            else "configured"
        )
        rows.append(
            {
                "id": surface["id"],
                "name": surface["name"],
                "required": required(surface),
                "stage": stage,
                "issue": problem,
                "record": row,
                "dashboard_path": "/" + path_for(surface) + "/home",
                "expected_permission": "read_only" if surface["profile"] == "wall" else "control",
            }
        )
    return {"revision": value["revision"], "epoch": house["epoch"], "users": users, "screens": rows, "issue": storage_issue or issue}


async def helper_state(core, row):
    helper = row["helper"]
    if not helper or not helper["id"]:
        raise ValueError("Helper creation is incomplete. Inspect native helpers before retrying; do not create duplicates.")
    async with core.websocket() as ws:
        helpers = await ws.command("input_button/list")
        registry = await ws.command("config/entity_registry/list")
    if not any(h.get("id") == helper["id"] and h.get("name") == helper["name"] for h in helpers):
        raise ValueError("The owned display helper changed or is missing.")
    entity = next(
        (e["entity_id"] for e in registry if e.get("platform") == "input_button" and e.get("unique_id") == helper["id"] and not e.get("disabled_by")), None
    )
    if not entity or helper["entity_id"] not in (None, entity):
        raise ValueError("Display helper registry identity changed or is unavailable.")
    return next((s for s in await core.states() if s["entity_id"] == entity), None), entity


def check_page(surface, entity):
    path = "home-starter-check-" + fingerprint([surface["id"], entity])[:12]
    content = (
        "## Check this display session\n\nOn the physical display, sign in with its dedicated account. "
        "Press the button below, then return to Home Starter on the administrator's device and read the check. "
        "This helper operates no household equipment.\n\n"
        f"[Open {safe(surface['name'])}](/{path_for(surface)}/home) · [Profile appearance](/profile/preferences)\n\n"
        "On the display: select its intended default dashboard in Profile → Appearance. "
        "Check the dashboard and required controls, then restart the browser/app/device normally and repeat the session check."
    )
    config = {
        "views": [
            {
                "title": "Display check",
                "path": "home",
                "cards": [
                    {"type": "markdown", "content": content},
                    {
                        "type": "button",
                        "name": "Verify this display session",
                        "entity": entity,
                        "show_state": False,
                        "tap_action": {"action": "perform-action", "perform_action": "input_button.press", "target": {"entity_id": entity}},
                    },
                ],
            }
        ]
    }
    return {"url_path": path, "config": config, "fingerprint": fingerprint(config), "surface": {"name": "Home Starter display check"}, "show_in_sidebar": False}


async def apply(core, store, house, publications, body, actor, now=None):
    now = now or datetime.now(UTC)
    value = load(store, house)
    common = {"revision", "epoch", "surface", "action", "confirm"}
    action = body.get("action")
    extra = {
        "select": {"user_id", "permission"},
        "restrict": {"user_id", "user_signature"},
        "local_only": {"user_id", "user_signature"},
        "begin": {"stage"},
        "observe": set(),
        "physical": {"dashboard_opened", "default_set", "controls_worked", "restart_kind"},
    }
    if (
        action not in extra
        or set(body) != common | extra[action]
        or body["confirm"] is not True
        or type(body["revision"]) is not int
        or type(body["epoch"]) is not int
    ):
        raise ValueError("Review and confirm the exact display action.")
    if body["revision"] != value["revision"] or body["epoch"] != house["epoch"]:
        raise ValueError("Display commissioning changed. Refresh before retrying.")
    surface = next((s for s in house["surfaces"] if s["id"] == body["surface"] and required(s)), None)
    if not surface:
        raise ValueError("Choose an existing fixed/shared screen.")
    users = await accounts(core, store)
    publication = next((s for s in publications if s["id"] == surface["id"]), None)
    if not publication or publication["status"] != "published":
        raise ValueError("The intended dashboard must match its published readback.")
    row = value["screens"].get(surface["id"])
    if action in {"select", "restrict", "local_only"}:
        user = next((u for u in users if u["id"] == body["user_id"]), None)
        expected = "read_only" if surface["profile"] == "wall" else "control"
        prepared = row.get("prepared") if row and row["user_id"] == body["user_id"] else None
        if action == "local_only":
            if (
                not user
                or not user["can_prepare"]
                or user["signature"] != body["user_signature"]
                or user["permission"] != expected
                or any(k != surface["id"] and r["user_id"] == user["id"] for k, r in value["screens"].items())
            ):
                raise ValueError("Review a suitable dedicated display account before enabling local-only access.")
            async with core.websocket() as ws:
                await ws.command("config/auth/update", user_id=user["id"], local_only=True)
            user = next((u for u in await accounts(core, store) if u["id"] == body["user_id"]), None)
            if not user or user["issue"]:
                raise CoreError("api", "Local-only account preparation could not be verified. Inspect its native settings before retrying.")
            prepared = {"at": now.isoformat(), "by": actor, "change": "local_only_enabled"}
        if action == "restrict":
            if (
                expected != "read_only"
                or not user
                or (user["issue"] and not user["can_prepare"])
                or user["permission"] != "control"
                or user["signature"] != body["user_signature"]
                or any(r["user_id"] == user["id"] for r in value["screens"].values())
            ):
                raise ValueError("Only an unassigned dedicated local non-admin account can be explicitly restricted for this passive wall.")
            async with core.websocket() as ws:
                await ws.command("config/auth/update", user_id=user["id"], group_ids=["system-read-only"], local_only=True)
            user = next((u for u in await accounts(core, store) if u["id"] == body["user_id"]), None)
            if not user or user["issue"] or user["permission"] != "read_only":
                raise CoreError("api", "Read-only permission change could not be verified. Inspect the native account before retrying.")
            prepared = {"at": now.isoformat(), "by": actor, "change": "read_only_and_local_only"}
        permission = body["permission"] if action == "select" else expected
        if not user or user["issue"] or user["permission"] != permission or permission != expected:
            raise ValueError("Select an active, local-only non-admin login with the expected permissions, separate from household-member accounts.")
        if any(k != surface["id"] and r["user_id"] == user["id"] for k, r in value["screens"].items()):
            raise ValueError("This account is already assigned to another fixed screen. Use a dedicated account.")
        if action == "select" and row and row["user_id"] == user["id"] and current(surface, row, publication, users) is None:
            return value  # Reconfirming the same valid binding must preserve physical evidence.
        row = {
            "user_id": user["id"],
            "permission": permission,
            "user_signature": user["signature"],
            "surface_signature": signature(surface),
            "dashboard_fingerprint": publication["fingerprint"],
            "helper": row["helper"] if row else None,
            "page": row["page"] if row else None,
            "attempt": None,
            "session": None,
            "restart": None,
            "physical": None,
            "prepared": prepared,
        }
        value["screens"][surface["id"]] = row
    else:
        problem = current(surface, row, publication, users)
        if problem:
            raise ValueError(problem)
        if action == "begin":
            if row["permission"] != "control":
                raise ValueError(
                    "Read-only accounts cannot press the native verification helper. "
                    "Session verification remains unresolved; do not promote this wall to commissioned."
                )
            if body["stage"] not in {"session", "restart"} or body["stage"] == "restart" and not row["session"]:
                raise ValueError("Verify the first session before starting a restart check.")
            if not row["helper"]:
                name = "Home Starter display check " + secrets.token_hex(6)
                row["helper"] = {"id": None, "entity_id": None, "name": name}
                save(store, value)  # An uncertain create response must never trigger duplicate creation.
                async with core.websocket() as ws:
                    result = await ws.command("input_button/create", name=name, icon="mdi:monitor-check")
                if not isinstance(result, dict) or not text(result.get("id"), 100):
                    raise CoreError("api", "Display helper creation could not be read back.")
                row["helper"]["id"] = result["id"]
                save(store, value)
            observed, entity = await helper_state(core, row)
            row["helper"]["entity_id"] = entity
            generated = check_page(surface, entity)
            records = {row["page"]["url_path"]: row["page"]} if row["page"] else {}
            row["page"] = await publish(core, generated, row["page"]["fingerprint"] if row["page"] else None, records)
            row["page"] = {k: row["page"][k] for k in ("url_path", "fingerprint")}
            row["attempt"] = {"at": now.isoformat(), "stage": body["stage"], "baseline": (observed or {}).get("state")}
            row["physical"] = None
            if body["stage"] == "session":
                row["session"] = row["restart"] = None
            else:
                row["restart"] = None
        elif action == "observe":
            attempt = row["attempt"]
            if not attempt or not timedelta(0) <= now - stamp(attempt["at"]) <= timedelta(minutes=15):
                raise ValueError("Start a fresh display session check; checks expire after 15 minutes.")
            observed, _ = await helper_state(core, row)
            async with core.websocket() as ws:
                live_page = await ws.command("lovelace/config", url_path=row["page"]["url_path"], force=True)
            if fingerprint(live_page) != row["page"]["fingerprint"]:
                raise ValueError("The native check page changed. Preserve those edits; session verification stopped.")
            if not observed or observed.get("context", {}).get("user_id") != row["user_id"] or observed["state"] == attempt["baseline"]:
                raise ValueError("No new press from the intended display user. Press the native check on that signed-in screen, then read again.")
            triggered = stamp(observed["state"])
            context_id = observed.get("context", {}).get("id")
            if not context_id or not stamp(attempt["at"]) <= triggered <= now:
                raise ValueError("Display evidence is stale or has an invalid timestamp.")
            if row["session"] and row["session"]["context_id"] == context_id:
                raise ValueError("Restart verification needs a new authenticated press.")
            row[attempt["stage"]] = {"at": triggered.isoformat(), "context_id": context_id, "user_id": row["user_id"]}
            row["attempt"] = None
        else:
            if (
                not row["session"]
                or not row["restart"]
                or not timedelta(0) <= now - stamp(row["restart"]["at"]) <= timedelta(minutes=15)
                or any(body[k] is not True for k in ("dashboard_opened", "default_set", "controls_worked"))
            ):
                raise ValueError("Verify both sessions and explicitly confirm the physical dashboard, default and required controls.")
            if body["restart_kind"] not in {"browser", "app", "device"}:
                raise ValueError("Choose the normal restart actually checked on the physical screen.")
            row["physical"] = {"at": now.isoformat(), "by": actor, "restart_kind": body["restart_kind"]}
    save(store, value)
    return value
