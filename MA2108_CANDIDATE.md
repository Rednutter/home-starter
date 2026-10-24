# MA 2.10.8 adaptation — local review candidate, not an upgrade recommendation

Baseline: published HS 0.8.47 and official MA 2.10.8 commit
24c14e8bf89de472ceb23ecbd33407bdfcccbd01. No live MA changes or publication.

The approved old repair archive is immutable and remains the only previously
approved artifact. This candidate is a separately generated archive and installer.
Its mere existence does not authorise installation, a restart or expanded access.

## Implemented candidate boundary

- The existing default guard version allowlist and 2.10.7 transfer pins remain
  unchanged. The new explicit native entry verifies eight exact upstream files,
  the model version, source origins and live wrapper identities. Only its own
  precisely defined startup insertion is normalised during source verification.
- Normal transport, queue edits and group control continue using MA public APIs.
  Their existing ownership, revision, occupied-player, uncertainty and capability
  checks remain. They can accept a separate authenticated native contract for
  2.10.8; matching read schemas or a version string alone cannot enable them.
- Contract responses are strict, feature-specific, server/app-bound and expire
  after five seconds. The service only obtains them over the existing bound MA
  connection and existing administrator scope. Missing/invalid contracts leave
  controls closed. Catalogue selection rechecks control authority before use.
- Finite transfer reuses native transfer plus the existing owner-preserving
  bridge, locks and uncertain-result journal. Protected Spotify/book/podcast
  transfers remain excluded. No independent duplicate streams are introduced.
- Audiobook/podcast progress and station-preview routing remain unavailable on
  2.10.8 in this slice. They have not been promoted by a generic contract flag.
- A stateless media-ID helper removes native discovery's dependency on UI/wall
  services. The offline bundle contains 13 modules and no household data. The
  legacy source installer also includes the helper dependencies; the frozen old
  repair archive was not regenerated or altered.

## Evidence and important finding

The isolated Python 3.14 harness verifies downloaded Git-blob/SHA-256 identities
before extracting exact official method bodies. It removes registration decorators
for testing, without modifying method bodies, and uses in-memory doubles only.
Passed cases cover playing, paused and idle transfer positions; radio starting at
zero; stopped-player clock corrections; separate users resuming the same book;
provider progress reports not echoing across accounts; external Spotify pause.

An unmapped provider-origin progress report can cause upstream to update all
users' playlog rows. Household code must reject unmapped ownership rather than
call that fallback. The candidate deliberately leaves progress routing closed.

These are method-level tests, not a running-MA or physical-house acceptance test.
Existing isolated tests additionally cover pool isolation, owner preservation,
stale revisions, expiry, changed sources and synthetic installation transactions.
No household providers, discovery, playback or credentials were used.

## Installer and rollback review

The new installer defaults to check-only and requires an explicit MA mass.py
target, MA 2.10.8/models 1.1.205, unchanged source pins and exact module hashes.
Applying to a reviewed target stages only the candidate package and exact startup
hook, retaining a verified .home-starter-2108-original backup. It performs no
restart, account creation, provider configuration, authentication or network change.
Unrelated existing adapter modules and conflicting backups cause refusal.

Rollback requires verifying the backup against the original mass.py source pin,
restoring that exact startup file and performing the separately authorised MA-only
restart. Leave candidate modules for inspection; removing their startup import
disables them. Never restore over unknown external edits without reconciliation.

## Remaining gates

Full MA startup/import, real provider/user context, group dissolution/DSP and
long-lived teardown/reconnect behaviour require an isolated Linux MA runtime.
This Windows host lacks POSIX resource; its official WebRTC build lacks OpenSSL
development files, and Docker Linux is unavailable. Method extraction does not
remove that gate. Cross-client native edits are not an atomic transaction.

Before publication: review this candidate diff, finish applicable packaged browser
checks and privacy, freeze a new source/artifact and run normal release CI.
Before recommending the MA upgrade: complete Linux runtime validation and review
the still-unsupported progress/station cases with an honest capability matrix.

Specific public-publication approval must cover the new native candidate entry,
installer/builder, control-contract service changes, identity-helper extraction,
tests and documentation. Exclude runtime archives, source downloads, logs, private
checkpoints, household evidence and the old native repair artifact.

Specific native activation approval must cover installing the newly reviewed
2.10.8 account-enforcement candidate and previously uninstalled finite-transfer
bridge, registering their administrator-only contract/transfer commands, changing
the exact startup hook and restarting MA only. This affects playback/account
enforcement and can briefly interrupt audio. No new credentials, provider/user
permissions, ports or persistent remote access are required. Earlier approval
for the old repair does not automatically approve this materially new artifact.
