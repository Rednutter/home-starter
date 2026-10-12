# Changelog

## 0.3.0

- Make the house usable: people, seven screen profiles, semantic admission,
  a 25-element capability catalogue, native Sections generation and room detail.
- Separate personal and physical-screen Pin / Hide / Reorder settings, stored
  locally in the App's backed-up `/data` directory.
- Administrator-reviewed dashboard creation/update with exact preview tokens,
  readback verification and protection for dashboards edited outside Home Starter.
- Explicit appliance completion transitions from HA recorder history; persistent
  last_run / runs_today / ran_today, daily rollover in HA's timezone and live
  Home Starter activity sensors. Missing history remains unknown.
- No dashboard projects, HA accounts, cloud analytics, inferred chores, calling
  service, entity removal or changes to existing inventory/MA flows.

## 0.2.0

- Fresh Batteries: optional household preparation and rescan at any time.
- Your home: rooms, floors, devices, entity relationships and conservative,
  explainable findings from supported Home Assistant registry APIs.
- Explicit administrator-only device room assignment with precondition checking
  and a fresh registry read to verify the result. No rename, merge or deletion.
- Lightweight reminders for hardware HA may not know about; choices are not saved.
- Music Assistant behavior and App permissions remain unchanged.

## 0.1.1

- Require an active Home Assistant administrator for setup operations.
- Verify the MA ingress listener, matching server version and completed
  onboarding; keep missing or ambiguous evidence unverified.
- Preserve unknown app/compatibility states on API failures, redact reflected
  tokens before error logging, and reject HTTP errors with success-shaped bodies.
- Restore UI controls after setup settles and reconfirm installation retries.
- Add adversarial regression tests for these cases.

## 0.1.0

- First version: read-only Home Assistant scan, and the "Music around the
  house" outcome that detects, installs/starts or hands off to Music Assistant,
  verifies it and opens it.
