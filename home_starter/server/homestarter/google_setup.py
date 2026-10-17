"""Native Google setup diagnosis. No OAuth credentials, URLs or raw errors are retained."""

from .core import CoreError

REDIRECT = "https://my.home-assistant.io/redirect/oauth"
GUIDE = [
    "Google Cloud Console → Select a project → New project (or use your existing project).",
    "APIs & Services → Library → Google Calendar API → Enable.",
    (
        "Google Auth Platform \u2192 Branding: complete App name, User support email and Developer contact information. "
        "Complete any required homepage/privacy fields before publishing."
    ),
    "Google Auth Platform → Audience → Publishing status → Publish app → In production. Testing grants expire; adding test users is not durable setup.",
    "Google Auth Platform → Clients → Create client → Application type: Web application.",
    "Authorized redirect URIs: " + REDIRECT + ". If My Home Assistant is disabled, use the exact redirect URI shown by the native HA flow instead.",
    (
        "Home Assistant \u2192 Settings \u2192 Devices & services \u2192 \u22ee \u2192 Application credentials. Add the Google OAuth Client ID "
        "and Client Secret there. Replace stale credentials only after reviewing which integration uses them."
    ),
    "Continue in Home Assistant and sign in to Google yourself. Return here; Home Starter checks the connection and opens calendar review automatically.",
]
ISSUES = {
    "invalid_client": (
        "ready_for_authentication",
        (
            "OAuth client needs repair. Check the current Web application client and HA Application credentials for a "
            "missing, bad or stale client. Then retry Google setup."
        ),
    ),
    "testing": (
        "ready_for_authentication",
        (
            "Google app is in Testing. Google Auth Platform \u2192 Audience \u2192 Publish app \u2192 In production. Complete required "
            "Branding fields first; then reconnect for durable authorization."
        ),
    ),
    "branding": (
        "ready_for_authentication",
        (
            "Publication is blocked by Branding. Complete the fields Google marks as required, including app name, support "
            "and developer contacts and any requested homepage/privacy URLs, then publish from Audience."
        ),
    ),
    "redirect_uri_mismatch": (
        "ready_for_authentication",
        (
            "Redirect URI mismatch. Google Auth Platform \u2192 Clients \u2192 your Web application \u2192 Authorized redirect URIs. Copy "
            "the exact URI shown by HA; the standard My Home Assistant value is"
        )
        + REDIRECT,
    ),
    "api_disabled": (
        "connected_but_incomplete",
        "Enable Google Calendar API in APIs & Services → Library for the same project as the OAuth client, then retry.",
    ),
    "invalid_grant": (
        "reauth_required",
        "Google authorization expired or was revoked. Re-authenticate the existing Google integration in HA; retained calendar choices will be reused.",
    ),
    "access_denied": (
        "ready_for_authentication",
        (
            "Google denied consent. If the page says the app is in Testing, publish it from Google Auth Platform \u2192 Audience "
            "\u2192 In production. Otherwise check account/organization restrictions and grant calendar consent."
        ),
    ),
}


def diagnose(error):
    # Inspect only in memory; return a fixed code/message. Never echo upstream text.
    value = str(error).casefold()
    for needles, code in [
        (("invalid_client",), "invalid_client"),
        (("redirect_uri_mismatch",), "redirect_uri_mismatch"),
        (("branding",), "branding"),
        (("testing", "test user"), "testing"),
        (("accessnotconfigured", "service_disabled", "api disabled", "calendar api has not been used"), "api_disabled"),
        (("invalid_grant", "revoked", "expired", "reauth"), "invalid_grant"),
        (("access_denied", "403"), "access_denied"),
    ]:
        if any(n in value for n in needles):
            state, detail = ISSUES[code]
            return {"code": code, "state": state, "detail": detail}
    return {
        "code": "unknown",
        "state": "failed",
        "detail": "Google setup needs attention. Open the native integration for its diagnostic, then retry. Saved calendar choices are preserved.",
    }


async def inspect(core, inventory, calendars, *, verify=False):
    entries = [e for e in inventory["integrations"] if e["domain"] == "google"]
    credentials = None
    try:
        async with core.websocket() as ws:
            records = await ws.command("application_credentials/list")
            credentials = any(r.get("domain") == "google" for r in records)
            # Never return, log or persist the credential records themselves.
    except CoreError:
        pass
    state, detail = "not_detected", "Connect Google Calendar. Home Starter will discover calendars after you return."
    issue = None
    if entries:
        loaded = any(e.get("state") == "loaded" and not e.get("disabled_by") for e in entries)
        if loaded:
            usable = [r for r in calendars["rows"] if r["available"] and r.get("source", {}).get("integration") == "google"]
            state = "connected" if usable else "connected_but_incomplete"
            detail = (
                "Review calendars"
                if state == "connected"
                else ("Google is connected but no usable calendar entities were created. Check calendar access and entity discovery in the native integration.")
            )
            if verify and usable:
                from datetime import UTC, datetime, timedelta
                from urllib.parse import urlencode

                now = datetime.now(UTC)
                query = urlencode({"start": now.isoformat(), "end": (now + timedelta(days=1)).isoformat()})
                try:
                    raw = await core.rest_get("/calendars/" + usable[0]["id"] + "?" + query)
                    if not isinstance(raw, list):
                        raise ValueError("Unsupported calendar read")
                    credentials = "verified_by_connection"
                except (CoreError, ValueError):
                    state, detail = (
                        "connected_but_incomplete",
                        "Google entities exist but their calendar feed could not be read. Repair or re-authenticate the native Google integration, then retry.",
                    )
        else:
            issue = diagnose(" ".join(str(e.get("reason") or e.get("state")) for e in entries))
            state, detail = issue["state"], issue["detail"]
    elif credentials:
        state = "ready_for_authentication"
    return {
        "state": state,
        "detail": detail,
        "credentials": credentials
        if isinstance(credentials, str)
        else "present_unverified"
        if credentials
        else "missing"
        if credentials is False
        else "unknown",
        "issue": issue,
        "route": "/config/integrations/integration/google" if entries else "/config/integrations/dashboard/add?domain=google",
        "guide": GUIDE,
        "redirect_uri": REDIRECT,
    }
