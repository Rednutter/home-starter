# MA update resilience — 0.8.47 compatibility engineering evidence

0.8.46 publication is complete separately: main
48a4b19ae960ffecc80a7db3268d40a0fd1b8ad9, CI run 40058478418 passed.
This worktree has no new commit, push or live activation. Local integration is
present, tested and packaged locally; it has not been published or deployed.

## Findings

- The immutable approved repair installer patches MA's mass.py startup hook and
  verifies a reviewed baseline for 2.10.6/2.10.7. Image updates can remove it.
- Account enforcement wraps private audio resolution/buffer/mapping functions
  and Soloist _acquire_run. Signature and wrapper-identity checks protect strict
  account leases. Removing the checks is not an update strategy.
- The separate, uninstalled transfer bridge hashes five queue/player internals
  and relies on native user context/locks. Public transfer APIs exist, but their
  equivalence for our owner, account, timer and progress guarantees is unproven.
- The uninstalled radio receiver correction also hashes private audio, Player
  and Cast implementations. Household UI sanitation is separately controlled.
- Read-only metadata and multiple control modules hard-code 2.10.7, independently
  of the sensitive adapters. The pinned MA frontend is a separate build version;
  its household adapter can preserve UI while server response contracts evolve.
- Existing guard/transfer tests use synthetic doubles. They do not establish
  compatibility with arbitrary real MA releases or physical playback.

## First prepared slice

ma_compatibility.py is a bounded read-only preflight, integrated locally with
protected admin diagnostics and catalogue bootstrap. It validates identity, schema,
explicit profile-to-native-user bindings, provider/user fields, source mappings,
player response shapes and a one-item library sample. Four existing read commands
run with bounded independent timeouts. No response payloads, credentials or native
IDs are exposed in diagnostics. Missing/empty/changed mappings fail closed.

An unknown release number may pass limited read-shape contracts; that result
explicitly authorizes neither data access nor playback. Request-time policy must
still apply. Spotify and transfer remain false regardless of version/shape.
No names, age, gender or provider labels are used to invent identity bindings.

19 focused synthetic tests pass, with Ruff check/format. Cases cover 2.10.6,
2.10.7, unchanged-contract 2.10.8/3.0.0/beta shapes, changed required fields,
invalid schemas/identity, empty/duplicate/missing source mappings, timeouts and
sanitised failures. These are not tests against running MA installations.

## Next bounded implementation

1. Wire read-only preflight into health diagnostics using existing credentials
   and verified native-user bindings, without replacing any playback gate.
2. Replace catalogue-only release-number checks with tested data contracts and
   profile/source checks. Give each unsupported feature an actionable reason;
   invalidate compatibility caches on server, schema, connection or filter change.
3. Add an isolated real-version contract matrix for reviewed versions and a
   candidate update. No household accounts/audio or live MA upgrade in that matrix.
4. Separately prepare a versioned native enforcement/transfer replacement, using
   public APIs where equivalent guarantees are demonstrated. A public API-only
   strict-provider/no-fallback replacement has not yet been established.
5. Keep the current repair bundle immutable. Any replacement affecting native
   security needs a separately reviewed artifact and specific activation approval.

Update procedure: preflight, preserve state/backups, maintenance approval, update,
verify basic reads and native enforcement, then controlled recovery/acceptance.
Do not blindly replay uncertain commands or release unknown leases. Do not alter
auto-update settings, providers, permissions, credentials or Google defaults.

Remaining gates: runtime integration and real-version testing; native repair's
existing console/access limitation; separate approval for public disclosure of
new compatibility code (0.8.46 approval does not cover this work); separate review
and approval for any replacement native adapter activation.

Primary references:
- https://www.music-assistant.io/api/
- https://github.com/music-assistant/client
- https://www.music-assistant.io/faq/masstransfer/
- https://www.music-assistant.io/settings/user-management/

## Latest checkpoint (supersedes the initial prepared-slice test status above)

Full local validation: 1,168 Python tests, 102 JS tests, Ruff check/format pass;
68 focused tests cover probes, integration and actual release-source contracts.
GET /api/music/runtime?compatibility=1 retains the existing administrator boundary
and does not call control/setup or write identity checkpoints. Catalogue bootstrap
can capture the existing unique-name policy only on reviewed releases into private
native-user IDs, bound to household/server/app/connection/profile identity. No
credentials or permission grants are stored; fresh filters still govern reads.
Unknown releases cannot seed the checkpoint. They can reuse verified IDs only
after bounded read checks. Old contexts are revoked on server/version/schema
change, without replay. Missing/empty filters, replacement users and corrupt
checkpoints fail closed. Native playback/transfer gates remain unchanged.

Official source matrix: 2.10.6 commit c24866405bd2068c25a60e1014e5ef8c3f6445bb and
2.10.7 commit 76ad754a68abdd0bfd179b13a2807d44771ddf90, 121 verified files each.
Required public-read declarations/parameters and six guard signatures match.
Five transfer pins match 2.10.7; four differ on 2.10.6, which remains unsupported
by that candidate. Both specify Python >=3.14 and models 1.1.205. The project test environment is
Python 3.12. Existing official uv/py inventory also identifies managed CPython
3.14.5, but that interpreter has no music_assistant, aiohttp or
music_assistant_models package. Docker's Linux engine is unavailable. No
daemon/start/install occurred.
Source declarations and synthetic tests do not attest running-server behaviour,
strict account isolation or physical playback.

The earlier atomic UI patch failure was corrected with targeted edits. Bootstrap
now reports a separate control-review requirement outside the existing 2.10.7
control baseline. The UI displays the reason, preserves read navigation and
profile selection, disables native transport/queue/group/timer controls and blocks
selection/action dispatch. Server selection also rejects that state. A passing
catalogue contract never clears native Spotify enforcement or transfer gates.

Packaged browser checks pass on desktop 1440x1000, tablet 1024x768 and phone
390x844 against fictional adapters: normal playback/queue/timer/group requests,
repeat-tap protection, profile isolation/navigation, discovery paging retry,
revoked old artwork, and unknown-version browsing with disabled controls.
No unexpected writes, external requests, page errors or CSP violations. These
are synthetic browser results, not household acceptance. Inspected desktop
fixture screenshot contains deliberately blank test covers, not real station art.
Privacy scan passed 905 source files; Ruff passed. No publication or native
activation is authorised by this checkpoint.

## Runtime test prerequisites and remaining limits

An isolated runtime matrix can use the already-present Python 3.14.5 interpreter
without changing system configuration. It still requires new disposable virtual
environments and installation of each official release's exact declared runtime
dependencies (including music-assistant-models 1.1.205), writable disposable
storage and loopback-only services. No such installation or MA process was run.
Alternatively the official images require an available Docker Linux engine;
its existing named pipe is absent. Do not start Docker or download/install a
runtime dependency set without the applicable authorisation. Use fictional
accounts/catalogue/player adapters: do not attach household providers or devices.
Run API/read/filter/reconnect tests before claiming any tested runtime version.
Source signatures alone cannot prove provider enforcement or native audio safety.

Native guard bundle remains byte-for-byte immutable. Its replacement needs a
separately reviewed security design/artifact and specific live approval. The
transfer candidate remains pinned to 2.10.7; four of five pins differ on 2.10.6.
Neither candidate has been installed during this work. Unknown versions can
reuse existing verified identity bindings only after bounded read checks; they
cannot create a new binding or gain controls by matching the catalogue schema.

## Exact proposed public publication scope (not yet authorised)

Only this local compatibility slice: ma_compatibility.py; catalogue_preview.py,
media_preview.py, music_runtime.py and the existing admin runtime diagnostic
branch in server.py; household frontend context/bootstrap/notice/control guards;
package_media_preview.py; official-release contract inspection tooling; focused
compatibility/integration/source tests and updated isolated discovery browser
test; this design/evidence note. A subsequent release would regenerate only the
matching production assets/notices/manifest, bump the add-on version and run CI.
Exclude private identity checkpoint files, runtime release-source downloads,
logs/screenshots, household payloads, native repair archives and unrelated work.
No new source commit, push, PR, release version or publication has occurred.


## Approved runtime attempt and 0.8.47 release review

The owner approved isolated official dependency installation and scoped public
publication on 24 October. Existing managed Python 3.14.5 was used in a disposable
venv. Official music-assistant-models 1.1.205 installed successfully. Executed
User/Artist/Player JSON/dictionary serializer roundtrips and contract validation
pass, including empty-filter rejection and no playback-authorisation claim. Both
reviewed releases declare this same model version; that is one model runtime,
not two running MA servers. CI repeats this model test on Linux/Python 3.14.

Registry-only resolution of full runtime dependencies passed. The complete
official dependency list also includes a vendor Git WebRTC dependency. Its exact
resolved commit native build failed because OpenSSL headers/crypto library are
absent (OPENSSL_ROOT_DIR / OPENSSL_CRYPTO_LIBRARY / OPENSSL_INCLUDE_DIR). The
official MA entry point also imports POSIX resource, absent on Windows. Docker's
Linux engine remains unavailable. No system toolchain/OpenSSL/daemon changes
were made. Full MA server startup and HTTP/WebSocket runtime matrix therefore
remain untested; no household accounts, discovery or audio were involved.

Release scope is 0.8.47 with the tested 481-asset manifest
180ba432af1a922f339ef5236caec6d4a7aebda057ad50286a1409a5d6664e41.
Native enforcement/transfer signatures and immutable bundle are unchanged. This
release does not promise arbitrary future MA updates will preserve playback.
It adds safe, diagnosable read compatibility while keeping unproven controls
closed. Existing admin/ingress and approved household listener boundaries stay
unchanged. Installation and post-update real-house acceptance remain separate.
