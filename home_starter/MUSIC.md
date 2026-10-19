# Music setup and verification

Music Assistant installation/HA integration health is separate from Music readiness.
Home Starter never marks Music verified from installation, a Spotify Connect plugin,
or a player label alone.

## Current household media (0.8.39)

Collections combine connected household sources into Playlists, Podcasts,
Audiobooks, Albums, Artists, Tracks and Saved radio. Exact provider identities
merge; matching names alone do not. Paging and typed search keep large libraries
and search-only catalogues accessible. A saved podcast count is not the size of
the iTunes search catalogue. Partial source reads remain explicitly incomplete.

Native MA provider access was expanded only after administrator consent. That
choice is bound to this household/server and requires active account enforcement;
it is broader native source access, not a metadata-only MA permission. Personal
playback precedence and the House → House #2 → Grant allocator remain separate.
Renae stays pending and personal-only; children have no Spotify identities.

The wall reads live MA players and queues, groups metadata by actual queue owner,
and shows one Now playing entry per active group when no selected camera is
available. Station catalogue names take precedence over delivery/ad markers.

All eight intended speakers are selected for shared Home Starter surfaces,
including Living Area Speakers, Workshop Speaker and Master Bedroom Speaker.
Child destination permissions retain their existing room scope. Existing media
entity IDs remain intact; duplicate/legacy HA views were hidden, not deleted.
MA's configured groups are Kitchen Area (Kitchen Hub + Living Area Pi), Morning
Group (those two + children's rooms), and Everywhere (all eight speakers).
Membership was verified; audible synchronisation was not. Home Starter still
starts individual speakers only: native MA group configuration does not establish
working group starts in the Home Starter UI.

The Pi uses its native `bcm2835 Headphones` output for 3.5 mm audio to the stereo
amp; USB microphone/voice routing is separate. Audible radio was confirmed by the
user. The agreed analogue mixer level is −6 dB and MA was set to 10%; boot-time
mixer persistence has not been verified. This is not a household loudness calibration.

Connect using a dedicated MA API token from **MA → Settings → Profile**, entered
only in Home Starter's password field. The connection is checked before replacing
an existing one. Provider account passwords and sign-ins stay in MA. The token is
stored in private `/data/music-connection.json` (mode 0600 in the Linux App), never
returned, logged, stored in the browser, or included in household/readiness exports.
Revoking that token in MA disables the connection. Reconnect through the same field.

The authenticated API reads actual music providers and configured metadata without
configuration values. Music providers, disabled/unavailable configurations, built-in
URLs, and player/plugin providers are distinguished. If configuration access is
denied, Home Starter explicitly reports a loaded-only view. Add/repair guidance
opens MA; provider account authentication remains in MA. The explicit administrator
catalogue action can add native zero-login ABC Radio and iTunes Podcasts sources;
it cannot create Spotify accounts or accept provider passwords. See
[Household services](HOUSEHOLD_SERVICES.md) for commissioning boundaries and gaps.

Choose a connected source and an available, single ungrouped speaker. Play one item
from that source on that speaker in MA, then **Check selected speaker playback**.
The readiness check only observes; it never sends transport, queue, volume or
grouping commands. The separately authorised listening controls can operate
playback. The current read allowlist is defined in `music_runtime.READ_COMMANDS`.

The check requires matching source/queue/item/speaker identity, active playback
and fresh raw device timestamps. Advancing raw position is recorded separately;
extrapolated clocks never establish automatic progress. Speakers with infrequent
updates can be audibly confirmed, with automatic progress explicitly unverified.
Missing source attribution, stale feedback or a playing label alone never completes Music.
It waits up to twenty seconds for playback to start before sampling progress.
After observation, the same HA administrator must confirm **I heard it on this
speaker** within ten minutes. A negative answer removes the candidate. An older
valid check is preserved on failed/declined attempts.

Proof covers only that source and speaker, expires after 24 hours, and is checked
against server identity, connection generation, source availability, speaker identity
and group membership. Household reset invalidates proof through its epoch while
preserving the service connection. API connection and read-only verification are
available before commissioning Go; they neither apply household plans nor mutate MA.
Commissioning Retry consumes valid proof; installation alone stays incomplete.

Reviewed MA server versions: 2.10.6 and 2.10.7. This is an observed software
playback attribution plus human audible confirmation, not acoustic measurement. Other
sources, speakers and groups remain untested.

Sources: [MA API](https://www.music-assistant.io/api/) and
[pinned MA server](https://github.com/music-assistant/server/tree/2.10.6).


## AirTouch listener/destination boundary (0.8.13)

Custom focused Media separates `listener.id` from selected physical destination.
The current player supplies playback metadata/transport and feature-gated volume
or grouping. Choosing a destination alone never starts audio. Child default output
comes from explicitly assigned rooms; permitted alternatives are deliberate choices.
Raw player volume is labelled as the speaker's own scale until household loudness
calibration is commissioned.

The personal-listening UI contract supports separately owned audiobook positions,
Mine/Shared/House choices, delayed start (Now/5/10/15 minutes/At), countdown,
Cancel/Start now and sleep timers. The commissioned provider must own durable
listener identity, progress and scheduling; positions are never stored on a speaker
or advanced by the page before delayed playback starts. Real registered service
descriptors and fresh revisioned owned state are required. Readiness currently
produces no such binding, so ordinary dashboards show Personal library not connected.
Music Assistant/Audiobookshelf/account wiring remains separate commissioning work;
fictional adapter tests prove UI contracts, not audible playback or provider support.
See [AirTouch](AIRTOUCH_PANEL.md) for the complete source/action boundary.


## Cast long-form progress (0.8.22)

Native playback acknowledgement precedes session assignment. A new queue uses MA's
start-from-beginning intent without a redundant Cast zero seek. Reusing the same
episode queue for a different listener forces a confirmed zero reset. Resuming a
listener's position requires fresh physical feedback and the same owned MA queue
after the explicit seek. Cast stream offsets are kept separate from raw elapsed time.

Some Cast players expose only their initial raw anchor during playback. Home
Starter can then save MA's frozen queue position only after its own explicit pause
has been acknowledged by both the matching device and queue. Stop and sleep timers
use that same capture path. Stored positions record `device_position` or
`ma_paused_queue` provenance. This does not weaken the separate Music readiness
proof, import provider-global resume or treat an ordinary running queue clock as
verified device progress. Provider and hardware behavior still require live checks.
