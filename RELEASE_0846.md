# 0.8.46 — faster usable startup and paged discovery

IN PROGRESS: performance release; installed speed improvement remains unverified.

Measured live 0.8.45 through the existing approved LAN read routes:

| Operation | Seconds | Response bytes |
| --- | ---: | ---: |
| Entry HTML | 0.047 | 11,176 |
| Cold catalogue bootstrap | 5.320 | 3,315 |
| Second bootstrap | 2.103 | 3,315 |
| Artists read | 0.165 | 128,813 |
| Radio cold | 2.097 | 1,177,820 |
| Radio cached | 1.064 | 1,177,820 |
| Podcasts | 0.188–0.256 | 15,991 |

Three permitted artwork samples returned in 0.083–0.100 seconds on first/cached
reads. These are HTTP measurements, not browser paint or physical-device tests.

The source awaited full, serial account/library preparation before mounting the
UI. Radio then issued capabilities and returned over 1,000 models despite showing
24 cards. Those are measured/code-confirmed software bottlenecks.

Changes: mount the shell before network work, gate routes/actions until household authority and profile mappings are
verified, return a minimal authority/provider bootstrap, defer library
loading, and read independent libraries/accounts concurrently. Discovery requests
explicit pages and receives a total count; unpaged callers remain compatible.
Only visible-page rows receive image/selection references. Missing or changed
source filters fail closed before/after loading. A cancelled reader does not
cancel another reader's shared load. Failed paging leaves the former page intact.
No fictional/stale catalogue is silently substituted or automatically selected.

Local verification includes a deliberately withheld bootstrap with visible
navigation, 1,000-row server pagination, source changes and cancellation,
failed-page retry/back, profile/art isolation, responsive layouts and the existing
mocked playback/queue/timer/group/transfer regressions. No live audio was started.

BLOCKED: live browser inventory remains apps=[] and browsers=[] despite the
owner opening a tab. No live visual/browser timing acceptance is claimed.
Current Green CPU, memory and resource contention are not available through the
approved read surface; rejected management credentials were not retried.

Hosting assessment: no measured basis for moving HA/MA/HS yet. A faster host
would retain the blocking startup and oversized responses. Fix software first,
then compare installed cold/warm timings and obtain authorised resource readings
if delays remain. No migration, new ports, accounts or permissions are included.

Deployment/rollback: normal Home Starter update only, with backup enabled and no
active sleep/delayed jobs requiring preservation. Keep the 0.8.45 backup. Existing
management access remains unavailable; use the signed-in HA updater. Native
account/transfer repairs, HA climate changes and full household cutover remain
separate. No additional preview, access expansion or new security setting.
