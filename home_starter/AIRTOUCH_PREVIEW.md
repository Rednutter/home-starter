# Isolated AirTouch preview — prepared, not published

Publication approval is pending. This preview is for layout, information and shallow
navigation review. It does not establish HVAC, audio, camera, native-control or family
acceptance. No service replacement/restart, account, permission, port, launcher,
default dashboard, Google routine or managed household surface change is included.

## Local generation and review

Use the trusted locally generated landscape configuration, with current authorised
source selections. Do not pass arbitrary or externally supplied executable dashboard
code. The guard is a UI side-effect boundary for these reviewed templates, not a
security sandbox or a change to the signed-in HA user's existing rights.

```python
from homestarter.panel_preview import prepare, verify

prepared = prepare(generated["config"], generated["url_path"])
verify(prepared, generated["config"], generated["url_path"])
```

`prepare` deep-copies its input; it never authenticates, reads HA, publishes or writes
files. It returns a configuration, source/result fingerprints and review manifest.
The destination is `home-starter-airtouch-preview`. Source surface/person/epoch scope
and selected context entities stay intact; only navigation addresses change. Existing
styles and compiled page renderers are reused. Native control cards become read-only
state summaries in their containing layout: their interactive appearance/behaviour
is deliberately outside this preview's acceptance. Kiosk overrides are omitted to
retain normal HA operator chrome; this does not change the production kiosk.

Review the diff and manifest before any separately authorised publication:

- All view paths retained and unique; every preview link stays inside the preview.
- Existing House/person/source/epoch mappings retained, with no new publisher record.
- Every embedded template has the preview facade. No native features/service actions
  or entity-picture consumers remain. Do not add external frontend resources.
- HA state reads remain; missing values stay unavailable. The facade removes image
  references, disables media ingress/bootstrap and blocks fetch, callWS and callService.
  It drops original DOM action callbacks, disables inputs/forms/buttons, removes
  mutation data attributes and admits only preview navigation anchors. This includes
  keyboard-generated clicks and repeated taps. Camera/image loading is suppressed.
- The dedicated `/media` app/new backend is not installed by this dashboard preview.
  Unavailable Media remains honest rather than using synthetic household content.
- Do not put the generated real-house configuration, backups or screenshots in Git.
  Keep any necessary private review/readback evidence under ignored `.runtime`.

Before a write, run `verify` against the unchanged reviewed source. Any changed source,
guard, manifest or configuration requires regeneration/review. Synthetic checks are
`pytest tests/test_panel_preview.py` and `python devtools/e2e_panel_preview.py`.

## Publication — approval still required

1. Read/back up existing dashboard registry, original AirTouch configuration and
   fingerprints through existing authorised HA access. Confirm the preview address
   is unused; stop on collision or concurrent edits. Recheck registered button-card.
2. Create only the preview registry entry using `lovelace/dashboards/create`, title
   `AirTouch · view-only preview`, `show_in_sidebar=false`. Match the original entry's
   `require_admin`; stop if this would require new access for the existing tablet user.
3. Save `prepared["config"]` with `lovelace/config/save` at the preview URL path;
   read back with `lovelace/config`, `force=true`. Require exact config/fingerprint
   agreement. Inspect uncertain outcomes before retrying; never overwrite a collision.
4. Verify original AirTouch/kitchen-wall/other saved dashboards and household settings
   are unchanged. Do not add this clone to Home Starter's managed publication records.
5. Grant temporarily opens the HA preview URL in the existing AirTouch browser/session.
   Keep the current launcher/startup/default URL. If locked, use an existing operator
   navigation mechanism; do not alter kiosk or security settings. Return to the saved
   original dashboard URL after review. Do not log out or create a new session/account.
6. Remove only this verified preview entry through HA dashboard administration when
   finished. Compare its current fingerprint first; preserve/inspect external edits.
   Read back the registry to verify removal and recheck the original fingerprints.

Use the existing HA address after rechecking it. At the last inspection it was
`http://192.168.68.119:8123`; preview suffix is
`/home-starter-airtouch-preview/home`. The HVAC controller IP does not identify the
tablet. No hardware restart or household service interruption is required; the
AirTouch temporarily shows the preview while Grant reviews it.

This publication approval does not authorise MA enforcement repair/restart, radio or
transfer adapter installation, AirTouch integration host repair/Core restart, ABS,
controlled playback, new `/media` service deployment or household cutover.
