# Changelog

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
