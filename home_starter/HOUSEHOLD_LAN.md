# Restricted household audio access

The optional household socket is separate from Home Assistant administration.
It is disabled by default. The approved commissioning address is
`http://192.168.68.119:13379/`, for source peers in `192.168.68.0/24` only.
Port publication is not proof of working access: verify the observed client
address survives Docker forwarding; ambiguous proxy peers are denied.

Enable only after a scoped backup and a fresh timer/handoff check. Set the
existing app's options `household_lan=true`, `household_lan_surface` to the
reviewed shared surface ID, and `household_lan_binding` to the service digest of
`[household_epoch, surface]`. Publish only container `8098/tcp` as host `13379`.
An ordinary Home Starter restart applies this; MA and HA Core need no restart.
Changed surface/household identity invalidates the binding. A failed secondary
listener leaves authenticated administration available.

Only the audio page, its named assets and household listening endpoints exist
on this router. HA, Supervisor, configuration, provider setup, arbitrary native
commands and all other routes remain unavailable. The existing ingress peer
guard and HA administrator verification are unchanged.

Anyone on the subnet may choose a listening profile and use its permitted audio
controls. Profile selection does not authenticate a person. Existing server-side
source/player rules, occupied-queue confirmation, account leases and separate
progress remain authoritative. To control an existing session, choose its
original listening profile; selecting another profile does not reassign it.
Delayed starts and station configuration are not exposed on this listener yet.
Uncommissioned Spotify enforcement/transfer stays unavailable.

The address uses unencrypted HTTP, as approved. A random HttpOnly SameSite=Strict
browser context expires after 30 minutes; reopen the page to renew it. JSON
mutations additionally require the exact same Origin. No persistent credential,
account, router forwarding, cloud tunnel or Google routine is created.

Rollback: through authenticated HA/Supervisor, set `household_lan=false` and
remove the single `8098/tcp` host mapping, then restart Home Starter. Verify
port 13379 is closed and authenticated ingress still works. If reverting the
whole release, restore its verified scoped backup after removing this mapping;
recheck saved household/dashboard fingerprints. Do not restore unrelated HA or
MA data, and do not assume restoring an image removes a separately saved mapping.
