# Stopped-container trial preparation - not activation authority

Keep live MA 2.10.7 and HS 0.8.47 until the remaining gates below are resolved.
The new native candidate is not the immutable previously approved repair. No
upgrade, start/restart, migration, SSH setup or system/Docker repair is performed
by these tools.

**Activation blocker identified in official Supervisor 2026.10.3 source:** normal
stop removes the container and normal start recreates it. The Docker-only offline
copy procedure below is not a working Supervisor activation procedure. Do not
upgrade MA or execute native installation based on that CI result. Keep the
apply gate closed until an approved method survives Supervisor's lifecycle.

## Existing console route and prerequisites

The operator needs a monitor and USB keyboard on HA Green, retaining Ethernet, power
and radio adapters. `ha >` then `login` opens the existing root host console.
Do not infer SSH availability or use the previously rejected HA bearer token.
Coordinate HA browser actions with Blink; browser availability is not assumed.

The host script needs its existing `sh`, Docker CLI/local socket, `curl`,
`sha256sum`, `readlink`, `id`, `cut`, `cp` and `mkdir`. It needs no host Python:
Python runs in temporary, network-none official-image helpers. Missing tools,
different image identity or remote Docker context cause a stop, not installation.
Helpers mount only the dedicated staging work directory, never `/data`, the
Docker socket, household configuration or the backup archive. They add no ports.

Prepare an existing authorised file-transfer path or existing USB media for the
reviewed scripts, receipt and RC5 archive; do not expose a new file server or
format media. Green staging/console access is still a practical prerequisite.

## Reviewed source and default behavior

`stage_ma2108_offline.sh` defaults to check only. `--prepare` patches public-source
copies in a new staging directory, leaving the real container unchanged. It
requires a stopped target, exact immutable MA 2.10.8 image and eight source pins,
the RC5 archive hash, a matching backup receipt and a locally available immutable
MA 2.10.7 rollback image whose package version is checked without network access.
Both official amd64 and arm64 image digests were obtained from the verified
2.10.8 multiarchitecture index; Linux runtime CI exercises amd64 only.

RC5 SHA-256:
`1556814c2b172d9b184b4c20ef946527f4d1dfd394827bc488e0be28c8b229eb`.
This supersedes RC3/RC4 for the operator tool. Python behavior is unchanged;
RC5 fixes tar modes and canonical LF for code/manifest so Windows/Linux generate
identical archives, including a locally CRLF-normalised working file. Module
hashes cover those exact canonical bytes. Previous archives are preserved.
The original repair remains
`b9a5e655229137606e90f35c1bce00ee59def01b238172d39ca30737b6020a1d`.

The eight positional arguments after the optional mode are:

1. Confirmed MA container name (`app_d5369777_music_assistant` from records).
2. Exact reviewed official 2.10.8 image digest, already present locally.
3. Local RC5 archive path.
4. New absolute `/mnt/data/supervisor/share/hs-ma2108-...` work directory.
5. Existing backup archive path (read only for checksum on the host).
6. Local backup receipt JSON path.
7. Immutable locally available 2.10.7 rollback image identity.
8. Observed installed Supervisor version.

Do not substitute guessed image/container/version values. Each run requires a
new work directory; preserve prior results and reconcile uncertain outcomes.
Default/prepare modes make no target writes. They temporarily create only
isolated helper containers and retain public-source staging files.

Receipt schema: `schema: 1`, `ma_version: "2.10.7"`, `hs_version: "0.8.47"`,
`backup_sha256`, `rollback_image`, `scopes` containing exactly
`d5369777_music_assistant` and `6726420e_home_starter`, `stopped_consistent: true`,
and `recovery_key_available: true`. This records the operator's confirmed backup
prerequisites, not proof of a successful restore. Never store the recovery key,
provider credentials, user payloads or backup contents in the receipt or Git.

## Preventing an unguarded upgrade window

No Supervisor version is currently in `SUPERVISOR_REVIEWS`. `--apply` therefore
refuses before its first target write, even after preparation passes. A stopped
container alone cannot establish that an update will preserve that stopped state.

Official tag `2026.10.3`, commit `ca2273e2a7ae061a7377658fb704a0b919330fb8`,
uses `supervisor/apps/` (not the older `addons/` source paths). Review establishes:

- `apps/app.py:update` restarts only an app that was STARTED/STARTUP before update.
- `apps/app.py:stop` calls `instance.stop()`; `docker/app.py:stop` defaults
  `remove_container=True` and delegates that operation to the Docker interface.
- `apps/app.py:start` calls `instance.run()`. `docker/interface.py:_run` first
  stops/removes an old container, then creates and runs a new one from the image.

Sources: [app lifecycle](https://github.com/home-assistant/supervisor/blob/ca2273e2a7ae061a7377658fb704a0b919330fb8/supervisor/apps/app.py),
[Docker app lifecycle](https://github.com/home-assistant/supervisor/blob/ca2273e2a7ae061a7377658fb704a0b919330fb8/supervisor/docker/app.py),
[Docker interface](https://github.com/home-assistant/supervisor/blob/ca2273e2a7ae061a7377658fb704a0b919330fb8/supervisor/docker/interface.py).

Thus a manually created/copied stopped container is not retained by a normal
Supervisor start; a copied hook is lost. Restart through the app UI also passes
through stop/start. The old console handoff's patch-then-app-restart sequence must
not be assumed valid on this Supervisor version either. The immutable repair
archive remains preserved; its existence is not lifecycle compatibility evidence.

These are exact public-source findings, not fresh readback of the installed
Supervisor version or proof of live behavior. No update, stop, start or credential
change was performed. A supported durable pre-start/packaging route still needs
review; direct Docker start or image-tag substitution is not an approved workaround.

Before enabling application: inspect the actual installed Supervisor's update
lifecycle and normal UI/CLI behavior, bind a review to that exact version and
operation, ensure no auto-start/watchdog path can run unguarded MA during
update/staging, and resolve the container-recreation blocker above. Do not replace
this review with an operator confirmation flag.
The script does not itself upgrade MA or manage Supervisor/watchdog settings.

Once that gate and specific native activation authority exist, the intended
application order is modules, verified original startup backup, then patched
startup last. Every phase rechecks stopped state and exact image. A journal is
written before each copy; source/module/startup/backup readback is mandatory.
Failure or interruption leaves MA stopped for inspection; never blindly replay.
The operator must also exclude competing Supervisor/container operations during
the copy window; the checks are not an atomic lock against another administrator.

CI tests this Docker copy procedure directly on a newly created disposable,
network-none target, including its first guarded startup. It does not unlock the
production operator gate or establish HA Supervisor behavior/ARM64 acceptance.

## Rollback and stop checklist

- Before upgrade, retain a consistent stopped MA data/version backup and matching
  HS settings/data backup; confirm scope, checksum, recovery-key availability and
  usable restore access. Retain the old image and old native source/repair evidence.
- First prepare/review the required new HS release, with version/bundle/CI; no
  release or merge is implied here. Check timers/jobs before its scoped restart.
- Do not upgrade until a Supervisor-compatible activation route is reviewed and
  specifically approved. A stopped-update check alone is insufficient. Never
  broaden source/user permissions or substitute a direct Docker start silently.
- On source mismatch, unexpected running state, partial/uncertain copy or failed
  readback, leave MA stopped. Preserve staging/journal and inspect actual state.
- Restoring `mass.py` only disables the 2.10.8 hook; it does not undo an image or
  database migration and must not be presented as complete rollback.
- Full rollback restores MA 2.10.7 with its matching pretrial data through the
  verified normal restore route; restore HS 0.8.47 if needed. Recheck identities,
  source restrictions, leases and progress before resuming. No automatic playback.
- No rollback or native activation is automated by this preparation. Physical
  speaker tests, prolonged provider recovery and family acceptance remain separate.
