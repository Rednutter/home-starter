# 0.8.45 — populated discovery collections

IN PROGRESS: release preparation; no live acceptance claimed.

Radio/Podcasts load on entry and profile changes. Native MA editorial cards keep
the Artists/Albums design. Ambient/books/episodes use the same card component;
sources without artwork retain an honest fallback. All selections keep the
existing household service, account allocation and progress boundary.

Radio fallback resolves public, reviewed RadioBrowser UUIDs through configured,
permitted providers. Regional service identity is distinct from home location:
local labels require the existing Albury/Wodonga region. Australian fallback
stations are labelled as Australian, not falsely presented as a live popularity
chart. Native popularity order remains intact when no score is supplied.
Podcast suggestions use configured trending plus exact own saved identities;
unknown language and absent personal evidence remain explicit. Nothing is saved
or subscribed automatically. House music shelves are unchanged.

Read-only result cache: five-minute fresh lifetime, at most 24 keys, stale fallback
under one day only for failed permitted sources. Keys include person, source
policy/availability, region and attributed saved state. Artwork/selection tokens
are issued anew and rechecked after reads. No cross-profile fallback.

Validation: full Python/JS/Ruff/privacy, focused discovery/cache/image tests,
packaged mocked playback/group/transfer regression, and isolated responsive
discovery browser checks. Synthetic covers are not evidence of real artwork or
physical playback. Upstream source remains pinned to dc3caf60f124301a32e21bcb053523d2451a6bfa.

BLOCKED: original three screenshot pixels cannot be materialized because the
supported Library transfer helper calls unsupported Windows os.setxattr. Text
descriptions are available but are not pixel inspection. Supported live browser
inventory is empty. These checks remain explicitly unrun; no alternate access
or metadata-less Library transfer is attempted.

Deployment: publish only after exact-source normal amd64/arm64 CI passes. Install
Home Starter only through the existing HA add-on updater with backup enabled
when no delayed/sleep jobs are active. Existing management credential returned
401 and must not be retried. Current HA installation is separate from publication.
Keep 0.8.44 backup for rollback; restore app backup if required. No household data
migration, provider permission change, MA restart, native bridge installation,
Google routine change or default dashboard cutover is included.

BACKLOG: live real-artwork checks, provider-outage recovery and actual family
acceptance after installation; controlled audio acceptance remains separate.
