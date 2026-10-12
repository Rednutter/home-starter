# Home Starter

An open-source Home Assistant helper for a house that grew piecemeal. Get things
awake, see what HA knows about your rooms and devices, review explainable findings,
then take a small explicit action and check whether it worked.

V0.2 adds **Fresh Batteries + House Inventory** and preserves the V0.1.1
**Music around the house → Music Assistant** flow.

## Install

Requires Home Assistant OS or a Supervised installation (the App Store).

1. **Add the repository.** In Home Assistant go to **Settings → Apps → App Store**,
   open the **⋮** menu → **Repositories**, add
   `https://github.com/Rednutter/home-starter` and close the dialog.
   Or use this link:
   [Add repository to my Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FRednutter%2Fhome-starter)
2. **Install.** Find **Home Starter** in the App Store (refresh the store if it
   doesn't show), open it and press **Install**. Home Starter has no prebuilt image,
   so Home Assistant builds it on your machine; this takes a few minutes.
3. **Start** it, then press **Open web UI** (or use **Home Starter** in the
   sidebar). It opens inside Home Assistant through ingress; there are no ports
   to configure. Its sidebar panel is admin-only; installation also verifies
   administrator access on the server.

## Fresh Batteries and Your home

- Prepare the physical house with an optional checklist. **Scan now** works at any point.
- Browse rooms → devices → entities, with floors when available, disabled state,
  owning integrations, parent/child/sibling relationships and technical identity.
- Review **Needs a room**, **Needs attention**, **Possible duplicates**, **Possibly
  offline**, and **Already fine**. Each finding explains its evidence/confidence;
  a single snapshot never establishes retired hardware.
- Assign one device to a room after reviewing the exact old/new values. Only
  administrators can confirm; the result is verified with a fresh registry read.
  No rename, deletion, merging, bulk disabling or configuration changes.
- Remind yourself about hardware HA doesn't know about. Choices and future-use
  possibilities are page-local, not a persistent external inventory.

See [inventory rules, API adjustments and limits](home_starter/INVENTORY.md).

## Existing scan and Music Assistant

* **Scan (read-only).** Home Assistant and Supervisor versions, OS, machine and
  architecture, storage, installed apps, integrations and any that failed to set
  up, areas, unavailable entities, waiting repairs and Supervisor health. It
  uses only the Supervisor and Home Assistant APIs and never changes anything.
  A source that can't be read is shown as unavailable; the rest still shows.
* **Music around the house.** Detects Music Assistant from App Store metadata
  (the official `music-assistant/home-assistant-addon` repository, matched by
  URL, not a hard-coded slug), installed apps (including the beta/nightly
  channels), the app's state and web UI, the Music Assistant server itself, and
  the Home Assistant integration. You then see one of: not in the App Store,
  ready to install, can't be installed on this system, stopped, starting,
  running but not connected to Home Assistant (discovered / ignored / missing /
  disabled / failing), needs its own first-run setup, or **ready**.
* **Install Music Assistant** (after you confirm): adds the official repository
  only if it's missing, finds the stable app in the returned store metadata,
  checks it supports your system, installs it as a Supervisor background job
  with progress, starts it and waits for it to run. Repeating it never adds the
  repository twice or reinstalls; an installed-but-stopped app is just started.
* **Hand-offs.** If a step can't be done directly (permissions, failures,
  unsupported system) or needs you — confirming the discovered integration,
  Music Assistant's own setup and provider sign-ins — Home Starter takes you to
  the exact Home Assistant screen (the app's store page, the add-repository
  dialog, Devices & services, the integration page) and offers **Check again**
  when you come back. It also re-checks when you return to the page.
* **Verification** requires all of: Supervisor reports it installed and
  started, its internal ingress listener responds, its server version matches
  the installed app, first-run setup is complete, and one app-discovered
  integration is `loaded`. Multiple apps/entries and manual integrations stay
  unverified because public entry summaries don't expose server IDs or URLs.
  Provider sign-ins, speaker availability and playback require checks in MA.
* **Open Music Assistant** asks Home Assistant to navigate to the app's
  ingress panel (`/app/<slug>`, or `/hassio/ingress/<slug>` before HA 2026.2),
  using the frontend's own iframe navigation message, with a same-origin
  fallback.

## Permissions

`homeassistant_api` (registry reads and confirmed device room writes through Core) and
`hassio_api` with `hassio_role: manager`. `manager` is the lowest Supervisor role
that can list installed apps, read store metadata, add a repository, install
and start an app; the `default` role can only read `/…/info` endpoints. No
Docker socket, `full_access`, host network, host folders or extra
capabilities. The token stays in the server process: it's never sent to the
browser or logged, and responses are checked for it before they leave. Only
requests arriving through ingress (172.30.32.2) are accepted, and installing
needs a JSON POST from an authenticated ingress session, explicit confirmation
and a server-side check that the ingress user is an active administrator. Room
assignment uses the same user check and only writes `area_id`, with preconditions
and verification. Permissions are unchanged from V0.1.1.

## Current limitations

* Only Home Assistant OS / Supervised installs (it needs the Supervisor).
* No prebuilt image yet: the first install builds locally and needs internet
  access to `ghcr.io` and PyPI.
* Home Starter can't confirm the Music Assistant integration or do Music
  Assistant's own setup for you; it links to those screens and re-checks.
* The server check uses the internal ingress port reported by Supervisor, so
  changes to the public port or TLS settings don't bypass verification.
  A missing response leaves setup unverified. Browser ingress authentication
  and real playback still need acceptance testing.
* Only the music outcome is built. Other outcomes are shown as "Later".
* The scan reports problems; it doesn't fix them.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                        # backend, contract fixtures, ingress, token tests
node --test tests/js/routes.test.mjs    # frontend routing / navigation
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Run the whole thing locally against a contract-faithful fake Supervisor and a
simulated Home Assistant ingress:

```sh
export HOME_STARTER_DEV_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python devtools/mock_supervisor.py --scenario absent      # :8181 (+ fake Music Assistant :8195)
SUPERVISOR_TOKEN="$HOME_STARTER_DEV_TOKEN" HOME_STARTER_SUPERVISOR_URL=http://127.0.0.1:8181 \
  HOME_STARTER_ALLOWED_PEERS=127.0.0.1 HOME_STARTER_MA_PORT=8195 \
  PYTHONPATH=home_starter/server .venv/bin/python -m homestarter   # :8099
.venv/bin/python devtools/ingress_proxy.py                          # open http://127.0.0.1:8124/home_starter
```

`mock_supervisor.py --core-url http://127.0.0.1:8123 --core-token-file token.txt`
proxies the Core API to a real (throwaway) Home Assistant instead of fixtures.
`devtools/e2e_browser.py` drives the full flow in Chromium,
`devtools/capture_core_fixtures.py` refreshes the Core fixtures from a real
instance, `devtools/validate_app.py` runs the App linter schema and the
Supervisor's own config schema, and `devtools/container-sim/` builds and runs
the real image offline on a stand-in for the HA base image.

Layout: `repository.yaml` (App repository), `home_starter/` (the App:
`config.yaml`, `Dockerfile`, s6 service, Python server in `server/homestarter`,
static UI), `tests/` (pytest + node tests, API-shaped fixtures), `devtools/`.

License: MIT.
