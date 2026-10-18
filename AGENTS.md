# Working instructions

Search before broad reads; use targeted edits and tests. Preserve the touch shell,
person pages, climate, room navigation, screen identities and activity tracking.

The supplied Smart Family Morning Dashboard is the wall's canonical visual
composition: clock/weather hero, three avatar/person cards, right timeline and
secondary panel, readable household bar and selected camera/status area.
Restore that grammar with lighter tinted glass; do not remove cards/avatars or
move week-ahead into a bottom strip. Keep dynamic selection/state underneath.
Use existing permitted photos or initial circles; never invent household photos.
Wall cursors stay hidden across the kiosk document and HA shadow roots. Global
rules must be mounted-wall/route scoped and removed on interactive navigation.
Kitchen Wall uses labwc/Wayland: use its dedicated transparent cursor theme,
not an X11 cursor daemon. Preserve original settings and verify after reboot.
Evening normally previews tomorrow's people/rules/forecast without overrides.
Night mode runs 21:00–05:00: three compact people cards, confirmed school/kit/next
commitment and household chronology; hide classes/week detail. At midnight keep
the upcoming day and relabel Tomorrow to Today; restore full detail at 05:00.
Weather preview emphasises labelled High/Low; daytime emphasises Now. No arrows.
Pi output power is separate: off 22:00–06:00 Australia/Sydney using wlopm and the
user screen-power timer. Keep Chromium/audio/voice running; verify off and wake.
The monitor hotplugs on standby: retain labwc's auto-enable guard and explicit
wlr-randr wake; disabled HDMI with a NOOP fallback is a valid overnight state.
Explicit event links/calendar ownership win; a unique leading "Name · event"
calendar label may identify a confirmed person. Never infer school/kit/travel.
School timetables use explicit child/source mappings and dated native periods;
retain order/provenance, never infer clothing/equipment or rotating weeks.
Duplicate feed names require metadata/event previews, not name-only guessing.
Shared school content still requires Show consent and verified selected sources.
No class payloads or private wall screenshots in Git.

Commissioning follows prepare → authenticate/consent → resume → verify. Never
authenticate personal Google accounts, persist credential/session material in
source or fixtures, or treat discovery as calendar visibility consent. Calendar
previews are ephemeral, administrator-only and excluded from logs/settings.

Current household acceptance: six MA users; Spotify Grant, House and House #2
connected; Renae pending until authenticated. Children have no Spotify identities.
Reconcile existing users/providers; never rename or delete them automatically.

Allocator intent: House → House #2 → Grant → busy/takeover; Renae is personal-only.
MA provider preferences do not prove strict playback isolation. Keep allocator
execution unverified until account enforcement, native occupancy, personal
precedence, concurrent leases and stale recovery have end-to-end evidence.
Keep the MA startup adapter pinned to the reviewed source/version; image updates
remove it and require compatibility review before scoped Spotify can resume.
Reviewed versions are 2.10.6 and 2.10.7; do not silently broaden this allowlist.
An audio-key rejection is a playback-engine issue, not proof of expired OAuth.
Soloist requires the user's upstream terms/API-key/pairing steps and a matching
account. Never accept terms or copy these credentials into Home Starter data.
House #2 completed this boundary on 18 October 2026. All allocator tiers, busy,
personal priority, concurrent starts and native-stop recovery subsequently passed
live. New failures still require fresh evidence; never infer playback from login.
Soloist teardown recovery must use the recorded native lease and a current pin.
Never settle an active/paused, same-session or unrecognised run by URI/device name.

Household discovery uses provider catalogue searches and provider-only similar
tracks, never MA Infinite Mix or library fallback. Reserve before discovery, pin
continuation to that account, and retain queue/session ownership through reseeds.
Spotify sync-back must read false before optional MA-only mapping cleanup.
LiSTNR identity is an opaque catalogue ID; never persist delivery-session URLs.
Postcode disclosure to LiSTNR requires explicit consent; exact home coordinates
stay local. Keep source attribution and synthetic upstream fixtures with tests.

Run Python/JS regressions, Ruff and privacy checks. The isolated calendar-preview
browser acceptance is `python devtools/e2e_connections.py`. Keep live evidence
separate from synthetic tests and report exact blockers; do not release an
incomplete commissioning slice.
