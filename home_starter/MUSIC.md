# Music setup and verification

Music Assistant installation/HA integration health is separate from Music readiness.
Home Starter never marks Music verified from installation, a Spotify Connect plugin,
or a player label alone.

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
Home Starter observes; it never sends transport, queue, volume or grouping commands.
The read API allowlist is `providers`, `config/providers`, `players/all`,
`players/get`, and `player_queues/get_active_queue`.

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

Supported API contract: MA 2.10.6 / models 1.1.205. This is an observed software
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
