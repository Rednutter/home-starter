# Physical screen commissioning

Home Starter 0.6.1 keeps dashboard publication separate from a working physical
display. Existing 0.6.0 settings and publications remain usable.

## Supported HA boundary

Verified against disposable Home Assistant Core 2026.10.0 using its native
WebSocket commands, native frontend and real non-admin browser sessions.

| Operation | Mechanism and boundary |
| --- | --- |
| Inspect accounts and Person links | Admin `config/auth/list` and `person/list`; reject owner/admin/system/inactive and household-person accounts. |
| Prepare an existing display account | Explicit `config/auth/update` to enable local-only login; preserve credentials and existing display-only Person. |
| Passive wall permissions | Explicit native `system-read-only` group restriction; no permission upgrades. |
| Create account/credentials | HA provides admin `config/auth/create` and `config/auth_provider/homeassistant/create`. Home Starter hands off the complete credential step to Settings → People → Users, avoiding passwords and partially provisioned accounts. |
| Verify an authenticated caller | Native `input_button/create`, registry resolution and `input_button.press` state context. The context user must match the selected display account. |
| Publish a check page | A separate, owned native dashboard; intended household dashboards remain untouched. |
| Default dashboard | Set on the display in Profile → Appearance. `frontend/set_user_data` belongs to its calling user; the app must not change another user's preferences through its own identity. |
| Persistent session | Two fresh native caller checks with an explicit restart step between them. HA does not expose another user's live browser/session health to the app. |
| Actual hardware, landing page and controls | Explicit owner report after using the physical display; the same account on another device cannot prove hardware identity. |

A normal non-admin HA user can control ordinary household entities. Dashboard
selection is not an entity-access boundary. Passive walls prefer read-only;
read-only accounts cannot press the current verification helper, so that path is
explicitly unresolved and cannot be marked commissioned by this implementation.
The future Kitchen Wall is represented without changing or reflashing a Pi.

An existing Person linked to a display account may remain only when This House
has a current explicit `other` confirmation, no trackers, and exactly one matching
native Person link. Household member accounts remain excluded. Home Starter does
not create, rename, delete or unlink Persons as part of this flow.

## States and evidence

- **Configured:** a saved screen describes the intended surface.
- **Published:** the intended native dashboard exists and matches readback.
- **Authenticated:** a fresh native helper press identifies the dedicated account.
- **Commissioned:** that evidence, a second fresh press after restart, and an
  explicit owner report of landing/dashboard/controls all match the current setup.

The owner reports the restart method actually tested: browser, app or device.
These are historical checks, not continuous monitoring of session revocation,
browser-data clearing or future physical availability. Changed native account,
screen or dashboard fingerprints require fresh checks. Reconfirming an unchanged
valid account preserves its evidence. Selecting a different account clears proofs
and retains the owned resources for reuse.

The native helper operates no household equipment. Each attempt expires after
15 minutes; stale/future/replayed presses, missing caller context, wrong accounts,
and edited check pages fail explicitly. Helper identity is resolved from the native
registry, not an inferred entity name. Uncertain helper creation is reserved and
not repeated automatically; external dashboard edits are protected.

## Privacy and migration

The new private `screen-commissioning.json` sidecar has its own version, household
epoch and revision. It stores native account/resource IDs, permission expectation,
fingerprints and dated evidence. It stores no passwords or auth tokens. Unknown,
corrupt or future data is preserved and blocks writes rather than being replaced.
Household reset revokes the binding without deleting native users or resources.

Reading an existing installation creates no sidecar and rewrites none of the
0.6.0 household, This House, Music, readiness, context or publication files.
Existing fixed/shared screens begin as “Dashboard ready — display identity not
yet verified”. Personal phones retain their personal account setup. All new
mutation routes require a verified HA administrator, explicit confirmation and
current revision/epoch; existing commissioning safety gates still apply.

HA owns credential creation and recovery. An authenticated administrator can
create a native user without knowing the owner's password. If HA explicitly asks
for reauthentication, follow its prompt; use the supported recovery path when
necessary. Home Starter never retrieves passwords, edits auth storage or bypasses
the security boundary. Password changes must be entered and submitted by the owner.

## Acceptance

Focused tests cover account suitability, lifecycle, caller/replay/expiry checks,
read-only failure, ownership, unchanged-account preservation, changed binding,
strict schemas, migration preservation and admin-only routes.

Disposable native acceptance verifies a real non-admin session, climate target
change and restoration, native default-dashboard preference, browser-process
restart without signing in again, two native caller proofs, separate physical
report, app restart, and desktop/mobile views. Its physical report is a fixture
attestation: it does not establish a real AirTouch login or Android device reboot.
The test browser's private login storage is outside Home Starter and outside Git.

Release validation: 453 Python tests (42 focused screen tests), 18 JavaScript
tests, Ruff lint/format, installer/inventory/readiness/rerun/touch/commissioning/
Music browser flows, This House and Context desktop/mobile checks, four native
screen profiles with control restoration, eight native Context scenes and native
Context publication/restart acceptance passed locally. The staged privacy scan
and CI app lint/multi-architecture builds are required before Green deployment.
Actual Green state is reported separately from disposable acceptance.

## Real display handoff

Choose the intended existing screen in Screens → Physical screen commissioning.
Inspect or prepare its suitable dedicated account, then sign into HA on that
physical display. Set the default dashboard in that account's Profile → Appearance.
Prepare the harmless check page on the administrator device, press it on the
display and read the result back. Start the restart check, restart normally,
verify landing and controls, restore any temporary control changes, and press
again without signing in. Confirm only the physical checks actually performed.

## Primary references

- [HA users and authentication](https://www.home-assistant.io/docs/configuration/user-configuration/)
- [HA dashboard defaults](https://www.home-assistant.io/dashboards/dashboards/)
- [Supported access recovery](https://www.home-assistant.io/docs/locked_out/)
- [Native account API, Core 2026.10.0](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/config/auth.py)
- [Native local credentials API](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/config/auth_provider_homeassistant.py)
- [Calling-user frontend preferences](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/frontend/storage.py)
- [Native button helpers](https://github.com/home-assistant/core/blob/2026.10.0/homeassistant/components/input_button/__init__.py)
