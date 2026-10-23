# Isolated MA component preview

This is a local, fictional, read-only integration slice. It does not connect to
MA/HA, use credentials, play audio, publish a LAN port or replace the live app.

Pinned upstream: Music Assistant frontend `2.17.297.post1`, source commit
`dc3caf60f124301a32e21bcb053523d2451a6bfa` (Apache-2.0). The verified source and
its LICENSE are retained in `.runtime/ma-household-upstream`; the release wheel
matches the installed MA2.10.7 entry asset. Keep the native source unmodified.

Run `python devtools/ma_frontend_preview/prepare.py` after the pinned source and
frozen upstream dependencies have been prepared. It copies our entry only into
`household-preview/`, without replacing `src/`. From the upstream directory:

```
node node_modules/vite/bin/vite.js build --config household-preview/vite.config.ts
node node_modules/vite/bin/vite.js preview --config household-preview/vite.config.ts
```

Compiled preview: `http://127.0.0.1:18742/` on NebulaReborn only. Development mode
uses18741; prefer the compiled version for acceptance because dependency discovery
can reload a first development visit. Neither listener binds to the home LAN.
No service worker or remote font download is enabled.

The same upstream router object, native route records, LibraryArtists/Albums/
Playlists/Tracks, ArtistDetails/AlbumDetails/PlaylistDetails, ItemsListing, native
search, Back cache, helpers, translations and styling are reused. A thin shell
provides persistent Collections, separate profiles and a disabled player. Native
view preferences remain in tab memory, separately per fictional profile. They
are not native user-management requests or persistent household writes.

The server adapter projects explicit fictional ownership/visibility, combines two
overlapping example source pages by canonical URI, retains source mappings and
pages results. Different same-named playlists remain distinct. House shelves admit
explicitly classified music tracks/artists/playlists; ambient or unknown
classification is excluded. Personal shelves use only their explicit ownership
projection. These fixtures demonstrate contracts, not real account attribution.

All unknown/native mutation commands are denied; there is no upstream proxy.
Profile/route generations discard late content. Missing counts remain unknown,
and failed lists display an unavailable message while navigation stays usable.
The source/playlist/recency assumptions must be reconciled with real household
metadata before integrating a production gateway.

Checks:

```
node --test devtools/ma_frontend_preview/projection.test.mjs
python devtools/e2e_ma_frontend_preview.py
```

Screens/evidence use fictional content and stay in `.runtime/ma-consumer-preview`.
No private household screenshots or payloads belong in Git. This slice does not
validate playback, grouping, account leases, native progress or family usability.
Its full upstream route module currently brings unused chunks into the build;
trim the production bundle and include upstream/dependency notices before release.
