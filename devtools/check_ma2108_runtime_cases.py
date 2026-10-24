"""Synthetic boundaries around real running MA controllers; no physical acceptance."""

import asyncio
import json
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch


async def account_cases(mass):
    from home_starter_ma.ma_account_guard import _pin
    from home_starter_ma.spotify_leases import AccountsBusy, SpotifyLeases
    from music_assistant.controllers.player_queues.state import PlayerQueueData
    from music_assistant_models.auth import User
    from music_assistant_models.enums import PlaybackState
    from music_assistant_models.media_items import ProviderMapping, Track
    from music_assistant_models.player_queue import PlayerQueue
    from music_assistant_models.queue_item import QueueItem

    guard = mass.home_starter_account_guard
    # Stop only this disposable guard's periodic task while fixture state is
    # installed; explicit recover calls below exercise its real lease engine.
    guard.task.cancel()
    await asyncio.gather(guard.task, return_exceptions=True)
    guard.task = None
    providers = {}
    for index, name in enumerate(("House", "House #2", "Grant", "Renae")):
        identity = "synthetic-spotify-" + str(index)
        provider = NS(instance_id=identity, name=name, domain="spotify", available=True, _sp_user={"id": identity})
        provider.get_setup_value = lambda key, identity=identity: {
            "playback_backend": "librespot",
            "librespot_credentials": json.dumps({"username": identity}),
        }.get(key)
        providers[identity] = provider
    users = {name.lower(): User(name.lower(), name.lower(), "user", display_name=name) for name in ("Edie", "Renae", "Grant")}
    queues = {}
    for i in range(5):
        qid = f"synthetic-{i}"
        media = Track(
            item_id="synthetic-track",
            provider="synthetic",
            name="Synthetic",
            provider_mappings={ProviderMapping(item_id="synthetic-track", provider_domain="spotify", provider_instance="synthetic")},
        )
        item = QueueItem.from_media_item(qid, media)
        queue = PlayerQueue(qid, True, "Synthetic", True, 1, state=PlaybackState.PLAYING, current_item=item)
        queues[qid] = PlayerQueueData(queue, items=[item], userid="renae" if i == 4 else "edie", session_id=f"synthetic-session-{i}")
    original_data = mass.player_queues._queue_data
    original_providers = mass._providers
    original_identities = dict(guard.identities)
    try:
        mass._providers = providers
        mass.player_queues._queue_data = queues
        with (
            patch.object(mass.webserver.auth, "get_user", AsyncMock(side_effect=lambda uid: users.get(uid))),
            patch.object(guard.engine, "grant_state", AsyncMock(return_value="idle")),
        ):
            await guard.configure_accounts({p.name: p.instance_id for p in providers.values()})
            leases = []
            for i in range(3):
                item = queues[f"synthetic-{i}"].queue.current_item
                lease = await guard.bind(item)
                item.streamdetails = NS(provider=lease["provider"], queue_session_id=lease["session"])
                leases.append(lease)
            assert [providers[lease["provider"]].name for lease in leases] == ["House", "House #2", "Grant"]
            marker = _pin.set(leases[0])
            try:
                for provider_id in providers:
                    mapping = ProviderMapping(item_id="synthetic-track", provider_domain="spotify", provider_instance=provider_id)
                    offered = mass.streams.audio._get_mapping_providers(mapping)
                    assert all(provider.instance_id == leases[0]["provider"] for provider in offered)
                    if provider_id == leases[0]["provider"]:
                        assert len(offered) == 1
                assert await mass.streams.audio._discover_alternative_provider_mappings(None, set(), 10) == set()
            finally:
                _pin.reset(marker)
            try:
                await guard.bind(queues["synthetic-3"].queue.current_item)
            except AccountsBusy:
                pass
            else:
                raise AssertionError("Shared overflow must never allocate Renae")
            personal = await guard.bind(queues["synthetic-4"].queue.current_item)
            assert providers[personal["provider"]].name == "Renae"
            old = dict(leases[0])
            queues[old["queue"]].session_id = "synthetic-reconnected-session"
            await guard.engine.recover(guard.providers())
            assert old["provider"] not in guard.engine.leases
            try:
                guard.check_pin(queues[old["queue"]].queue.current_item, old)
            except AccountsBusy:
                pass
            else:
                raise AssertionError("Old stream survived session replacement")
            restored = SpotifyLeases(guard.engine.path, guard.observe, guard.grant_state, guard.stop)
            assert old["provider"] not in restored.leases
            assert not await guard.stop(old)
            # A disconnected provider invalidates account integrity rather than
            # disguising a different account behind the same provider identity.
            providers[personal["provider"]]._sp_user = {"id": "synthetic-wrong-account"}
            assert not guard.account_integrity()[0]
        print("PASS runtime guard shared priority, personal isolation, persisted stale recovery and reconnect refusal", flush=True)
    finally:
        mass._providers = original_providers
        mass.player_queues._queue_data = original_data
        guard.identities = original_identities
        guard.engine.leases.clear()


async def progress_cases(mass):
    from home_starter_ma.ma_control_contract import check_progress_start

    # The upstream unmapped-provider progress fallback is not declared safe.
    # Assert our actual production entry guard refuses it before calling the
    # real music controller, for every profile context including absent owner.
    with patch.object(mass.music, "mark_item_played", AsyncMock()) as write:
        for owner in ("synthetic-one", "synthetic-two", None):
            for kind in ("audiobook", "podcast_episode"):
                try:
                    check_progress_start({"version": mass.version, "owner": owner}, kind)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unreviewed progress start was accepted")
        write.assert_not_awaited()
    print("PASS runtime unreviewed progress entry refuses all owners before controller write", flush=True)


async def group_cases(mass):
    from music_assistant_models.enums import PlaybackState, PlayerType

    controller = mass.players
    player = NS(
        player_id="synthetic-leader",
        name="Synthetic",
        native_grouping_requires_own_stream=True,
        extra_data={},
        state=NS(type=PlayerType.PLAYER, supported_features=set(), group_members=["synthetic-leader", "synthetic-child"], playback_state=PlaybackState.PLAYING),
    )
    with patch.object(controller, "_handle_set_members", AsyncMock()) as change:
        for state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
            player.state.playback_state = state
            assert not await controller._dissolve_own_group(player, "Synthetic target")
        change.assert_not_awaited()
        player.state.playback_state = PlaybackState.IDLE
        assert await controller._dissolve_own_group(player, "Synthetic target")
        change.assert_awaited_once_with(player, player_ids_to_remove=["synthetic-child"])
        change.side_effect = OSError("Synthetic disconnected device")
        assert not await controller._dissolve_own_group(player, "Synthetic target")
        change.side_effect = asyncio.CancelledError
        try:
            await controller._dissolve_own_group(player, "Synthetic target")
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancellation was swallowed")
    with (
        patch.object(mass.config, "get_player_dsp_config", return_value=NS(enabled=True)),
        patch.object(controller, "on_player_dsp_change", AsyncMock()) as dsp,
    ):
        controller._handle_group_dsp_change(player, ["synthetic-child"], [])
        await asyncio.sleep(0)
        dsp.assert_awaited_once_with(player.player_id)
    # A pending DSP restart must not resurrect a queue emptied during transfer.
    with (
        patch.object(controller, "get_player", return_value=None),
        patch.object(mass.player_queues, "get", return_value=NS(items=0)),
        patch.object(mass.player_queues, "resume", AsyncMock()) as resume,
    ):
        await controller._resume_queue_after_dsp_change("synthetic-empty")
        resume.assert_not_awaited()
    print("PASS real group/DSP controller active refusal, idle dissolution, disconnect, cancellation and empty-queue no-resume", flush=True)


async def transfer_cases(mass):
    from home_starter_ma.ma_release_review import ReviewedRelease
    from home_starter_ma.ma_transfer import NativeTransfers
    from music_assistant.controllers.player_queues.state import PlayerQueueData
    from music_assistant_models.auth import User
    from music_assistant_models.enums import PlaybackState, PlayerType
    from music_assistant_models.media_items import ProviderMapping, Track
    from music_assistant_models.player_queue import PlayerQueue
    from music_assistant_models.queue_item import QueueItem

    class State(NS):
        def to_dict(self):
            return dict(vars(self))

    media = Track(
        item_id="synthetic-local-track",
        provider="synthetic-local",
        name="Synthetic",
        provider_mappings={ProviderMapping(item_id="synthetic-local-track", provider_domain="filesystem", provider_instance="synthetic-local")},
    )
    item = QueueItem.from_media_item("synthetic-a", media)
    queues = {
        "synthetic-a": PlayerQueueData(
            PlayerQueue("synthetic-a", True, "Synthetic", True, 1, state=PlaybackState.PAUSED, current_index=0, current_item=item, resume_pos=42),
            items=[item],
            userid="synthetic-owner",
            session_id="synthetic-source-session",
        ),
        "synthetic-b": PlayerQueueData(PlayerQueue("synthetic-b", False, "Synthetic", True, 0), userid=None),
    }
    players = {
        pid: NS(
            player_id=pid,
            name="Synthetic",
            type=PlayerType.PLAYER,
            state=State(
                player_id=pid,
                type=PlayerType.PLAYER,
                available=True,
                playback_state=data.queue.state,
                active_source=pid,
                active_group=None,
                synced_to=None,
                group_members=[],
                static_group_members=[],
                elapsed_time=42,
            ),
        )
        for pid, data in queues.items()
    }
    owner = User("synthetic-owner", "synthetic-owner", "user", player_filter=list(queues), provider_filter=["synthetic-local"])
    controller = mass.player_queues
    previous = controller._queue_data

    async def stop(qid):
        queues[qid].queue.state = PlaybackState.IDLE
        players[qid].state.playback_state = PlaybackState.IDLE

    def clear(qid, **_):
        queues[qid].items = []
        queues[qid].queue.current_item = None

    try:
        controller._queue_data = queues
        with ExitStack() as stack:
            stack.enter_context(patch.object(mass.players, "get_player", side_effect=players.get))
            stack.enter_context(patch.object(mass.webserver.auth, "get_user", AsyncMock(return_value=owner)))
            stack.enter_context(patch.object(mass, "get_provider", return_value=NS(domain="filesystem")))
            stack.enter_context(patch.object(controller, "stop", AsyncMock(side_effect=stop)))
            stack.enter_context(patch.object(controller, "_clear", side_effect=clear))
            stack.enter_context(patch.object(controller, "_resolve_default_toggles"))
            stack.enter_context(patch.object(controller, "is_smart_shuffle_active", return_value=False))
            stack.enter_context(patch.object(mass.streams, "is_smart_fades_active", return_value=False))
            load = stack.enter_context(patch.object(controller, "load", AsyncMock(side_effect=OSError("Synthetic lost load response"))))
            bridge = NativeTransfers(mass, review=ReviewedRelease(mass))
            assert (await bridge.status())["pinned"]
            a, b = await bridge.snapshot("synthetic-a"), await bridge.snapshot("synthetic-b")
            args = ("synthetic-a", "synthetic-b", a["revision"], b["revision"], "a" * 32, False)
            try:
                await bridge.transfer(*args)
            except OSError:
                pass
            else:
                raise AssertionError("Synthetic partial failure was lost")
            assert load.await_count == 1
            assert queues["synthetic-b"].userid == owner.user_id
            assert queues["synthetic-b"].queue.resume_pos == 42
            assert await bridge.transfer(*args) == {"state": "uncertain"}
            assert load.await_count == 1
            assert queues["synthetic-b"].queue.current_item is item
            assert not queues["synthetic-a"].items
        print("PASS real native transfer body and player locks preserve paused owner/position on partial failure; uncertain retry never replays", flush=True)
    finally:
        controller._queue_data = previous


async def run_cases(mass):
    await account_cases(mass)
    await progress_cases(mass)
    await group_cases(mass)
    await transfer_cases(mass)
