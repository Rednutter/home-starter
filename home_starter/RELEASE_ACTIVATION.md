# Household Audio release and activation checklist

These are separate layers. Local tests are not physical-house acceptance.

| Layer | Exact source / state | Next gate |
| --- | --- | --- |
| Published Home Starter 0.8.43 | Release `13d680230c26e35017ba7aa16228c4ecad0a8577`; main merge `fd914e83308a3f1df70f3fe45717727bd060f218`. Release CI 39948149512 and main CI 39948452523 passed normal amd64/arm64 builds. | Install through the existing HA add-on update route after backup/preservation checks. |
| Newer shared/group features | Shared controls, existing-session grouping and idle group starts: `40265f9952616b4dc6a6034bd7b14f049c5beac5`. Bounded grouped-transfer source is in the local commit containing this checklist. | Not published or deployed. Needs a new versioned, reviewed UI bundle/manifest/notices and exact-source image CI before release. |
| Approved MA account repair | Immutable `ma-guard-bundle.tar`, SHA-256 `b9a5e655229137606e90f35c1bce00ee59def01b238172d39ca30737b6020a1d`. Approved scoped startup adapter and MA-only restart. | Physical HAOS root-console access, installed 2.10.7/source pin checks, backup and reviewed operator handoff. No new remote access. |
| Separate MA transfer bridge | Existing opt-in `ma_transfer.py` candidate is unchanged and uninstalled. Not included in the approved repair archive. | Separate exact-source compatibility/activation review before installation. No account, permission, credential or network expansion is implied. |

## Current access evidence

One read-only check of `http://192.168.68.119:13379/` returned HTTP 200 for
entry/bootstrap/media/script. It still references `static/media-app.js`, SHA-256
`4c3af929c2bb547509c8ad4ec2e854c06bb9a006074c73dfbb7b9eab0c216997`.
The legacy HTML hash is unchanged; 0.8.43's new assets have not appeared. No
installed version was exposed by these reads. No management credential was used.

## Shortest safe sequence

- Use an existing signed-in HA session: Settings -> Apps -> Home Starter. Check
  for 0.8.43, take/verify a scoped Home Starter options/data backup, preserve active
  timers/jobs and dashboard/default fingerprints, then update Home Starter only.
  Existing management authentication returned 401 and was not retried; no usable
  signed-in browser session is exposed to this executor. Never send tokens in chat.
- Verify the real LAN entry, assets and state after updating. Retain the 0.8.42
  backup/image/source `fb5d43ade11e5abce0a29ed185106aa41259c5a7` for scoped rollback.
- Arrange physical HAOS host-console access for the already approved MA repair.
  Follow the reviewed `GRANT_CONSOLE_HANDOFF.md`; verify the immutable archive and
  installed source before applying. The MA-only restart may interrupt audio.
- Package newer app features separately; do not relabel their local bundles as
  0.8.43. Activate no native transfer bridge until separately reviewed/authorised.
- Test actual player compatibility, ownership/account allocation, timers/progress,
  audible synchronisation and family operation in a suitable household window.
  Preserve Google routines, current defaults and all unrelated entities. This is
  not permission for a full household cutover, HA climate restart or ABS install.

## Bounded feature limits

The grouped-transfer implementation supports playing finite unprotected queues
and empty, compatible destinations. It preserves queue/position/native user,
owner history and sleep deadline; uncertainty never triggers blind replay.
Spotify/account-scoped media, audiobooks/podcasts, evolving queues, occupied or
saved-queue replacement, overlapping groups and paused grouped moves stay
unavailable. Earlier partial phases need explicit reconciliation; native-client
races are optimistic, not atomic. Full Spotify/progress handoff needs a separately
reviewed native contract, not a permission bypass.

Validation before this closeout: 1,132 workspace Python tests (34 new group-move
cases), 108 JS tests, Ruff, privacy and compiled fictional browser acceptance.
No further feature implementation is required for this bounded slice. Immediate
unblocked release work is packaging the reviewed source and image CI; actual
activation remains gated as above. Unrelated shelf/legacy edits remain preserved
outside these scoped commits.
