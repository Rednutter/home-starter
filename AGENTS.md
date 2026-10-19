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
Wall Now playing reads active MA queues, once per group, never deduplicated by
title. Radio shows catalogue station names; publish no raw queue/stream payloads.
The right timeline is one surface with a content-positioned future-day divider.
Pi music uses 3.5 mm to the stereo amp; Sendspin's PortAudio name is
`bcm2835 Headphones`, not the ALSA plughw string. Keep the USB mic independent.
Kitchen Wall uses labwc/Wayland: use its dedicated transparent cursor theme,
not an X11 cursor daemon. Preserve original settings and verify after reboot.
Evening normally previews tomorrow's people/rules/forecast without overrides.
From noon, school cards preview tomorrow's dated Cirrus periods independently of
today's household timeline/weather; never substitute today's periods when absent.
Night mode runs 20:00–05:00: quiet clock/date/weather and restrained home/media
status; omit all people/planning cards and timelines. Retain a single unboxed
school leave time only when all mapped children share that confirmed departure.
Restore full detail at 05:00.
Wallpapers are local generated landscapes with subtle hidden decorative details.
Keep one selection per morning/day/afternoon/evening/night, stable on reload and
across midnight; choose from each period's pool daily, never rotate within it.
Weather preview emphasises labelled High/Low; daytime emphasises Now. No arrows.
Weather stays two lines: balanced icon/inline temperature labels, then one brief
description. Extra text is reserved for meaningful weather exceptions.
Pi output power is separate: off 22:00–06:00 Australia/Sydney using wlopm and the
user screen-power timer. Keep Chromium/audio/voice running; verify off and wake.
The monitor hotplugs on standby: retain labwc's auto-enable guard and explicit
wlr-randr wake; disabled HDMI with a NOOP fallback is a valid overnight state.
Explicit event links/calendar ownership win; a unique leading "Name · event"
calendar label may identify a confirmed person. Never infer school/kit/travel.
School timetables use explicit child/source mappings and dated native periods;
retain order/provenance, never infer clothing/equipment or rotating weeks.
Confirmed school departure routines apply only to dated native school days.
Timetables use subtle person-tinted lesson cards with quiet times and current
period emphasis. Double lessons span their native slots; slim Recess/Lunch gap
cards retain shared bell-time positions. The user confirmed those two Cirrus
gaps as Recess/Lunch. Never invent periods or label other gaps without evidence.
Lesson cards show subjects only, with no times or multiplier badges; breaks are
slim unlabelled separators. Keep the full day contained and shared slot positions.
When selected cameras are unavailable, use that region for fresh playing media;
available cameras keep priority and stopped media leaves no empty card.
Duplicate feed names require metadata/event previews, not name-only guessing.
Shared school content still requires Show consent and verified selected sources.
Calendar commissioning consent is bound to source/choice identity, not a daily
expiry. Re-read native events each update; failed reads hide data and retry next
update. Preserve timetables in morning cards; promote confirmed Leave or native
Starts times without inferring kit/travel. Timeline times always mean Starts.
No class payloads or private wall screenshots in Git.

Commissioning follows prepare → authenticate/consent → resume → verify. Never
authenticate personal Google accounts, persist credential/session material in
source or fixtures, or treat discovery as calendar visibility consent. Calendar
previews are ephemeral, administrator-only and excluded from logs/settings.

Current household acceptance: six MA users; Spotify Grant, House and House #2
connected; Renae pending until authenticated. Children have no Spotify identities.
Reconcile existing users/providers; never rename or delete them automatically.
The user now requests shared collection metadata across all connected Spotify
identities: category buckets, not account folders. Deduplicate upstream IDs,
never titles; paginate rather than truncate. This sharing is catalogue metadata
only: direct personal provider access, allocator priority and playback leases
remain scoped. Renae contributes only after connection. No upstream sync-back.
The user additionally approved native MA provider access across all connected
Spotify identities for all six existing users. Persist separate administrator
consent, bind it to the household/server and require active pinned playback
enforcement before expanding native filters. Never infer this native-access
consent merely from requesting combined catalogue metadata.

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
