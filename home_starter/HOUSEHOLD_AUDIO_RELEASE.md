# Household Audio 0.8.44 release candidate

IN PROGRESS: draft release preparation only. No live deployment, native adapter
installation, provider permission change or household cutover is included.

## Exact artifact

Feature commits: shared transport/grouping/idle starts
`40265f9952616b4dc6a6034bd7b14f049c5beac5`; bounded grouped transfer
`e7f8fb5995b8b1a5337375b8b9e65f69caca1aef`.
The candidate contains 481 compiled assets plus the exact manifest and dependency
notices. Manifest SHA-256:
`cbc160d7dec3c75ca5cb48b7d6fe9723f226a5be039b920df209de4eb5797749`.
Upstream MA frontend remains 2.17.297.post1 at
`dc3caf60f124301a32e21bcb053523d2451a6bfa`, verified archive SHA-256
`3f13ca9cb443e877f0c29f170cb52a74cf10ee9081b532d895649c64efafcfef`.
Upstream source, frozen dependencies, licences and dependency inventory are unchanged.
Packaging writes canonical UTF-8/LF metadata on Windows and Linux.

## Behaviour and limits

Shared transport retains the listening owner and account/progress context.
Native grouping and idle multi-speaker starts use one managed leader; membership
changes require fresh permission/occupancy checks and explicit intent. Bounded
group moves preserve finite unprotected queues, position, native user, owner
history and sleep deadline between empty compatible destinations.

Spotify/account-scoped and audiobook/podcast moves, evolving queues, occupied or
saved-queue replacement, overlapping groups and paused grouped moves stay
unavailable. Partial/unknown phases do not automatically replay or roll back.
Native-client races remain optimistic, not atomic. Missing native protection or
transfer capability fails closed. The separate transfer bridge stays uninstalled.
The approved immutable MA account-repair archive is unchanged and separate.

## Validation and release gates

Exact isolated source: 1,129 Python tests; 108 JS tests; Ruff; 481 manifest/asset
checks; compiled fictional browser tests at desktop/tablet/phone sizes. Browser
navigation, profile isolation, transport, grouping, idle starts and group-move
review/cancel/double-confirm passed with no external requests, page errors or CSP
violations. These are synthetic checks, not audible or family acceptance.

Existing CI must rebuild the exact candidate, compare its assets and build the
normal amd64/arm64 Docker context. Images are not pushed or deployed. The draft
PR is for review; published 0.8.43/main remain unchanged during these checks.
Before any later deployment, verify a fresh scoped backup, actual installed image,
options/data, active timers/jobs and dashboard/default fingerprints. Use that
verified live version for rollback; do not assume published 0.8.43 is installed.
The last LAN asset read still served the legacy interface. Preserve the recorded
0.8.42 rollback and published 0.8.43 source as separate recovery references.

See RELEASE_ACTIVATION.md for the manual HA update route, physical-console MA
repair gate, separate bridge activation review and real-house acceptance sequence.
