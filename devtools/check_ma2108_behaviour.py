"""Run verified upstream 2.10.8 methods with isolated in-memory doubles.

Requires Python 3.14 and the official pinned models. No MA server, provider,
network or household device is started. Function bodies are extracted unchanged;
only decorators are omitted so API registration does not execute in this harness.
This is method-level evidence, never full-server or physical acceptance.
"""

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import cast
from unittest.mock import AsyncMock, Mock

COMMIT = "24c14e8bf89de472ceb23ecbd33407bdfcccbd01"  # pragma: allowlist secret -- official public release


def method(root, file, name, namespace):
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["commit"] == COMMIT and manifest["version"] == "2.10.8"
    relative = "music_assistant/" + file
    body = (root / relative).read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["files"][relative]
    tree = ast.parse(body.decode())
    node = copy.deepcopy(next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name))
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(root / relative), "exec"), namespace)  # noqa: S102 -- exact verified official source, isolated namespace
    return namespace[name]


async def run(root):
    from music_assistant_models.enums import EventType, MediaType, PlaybackState, PlayerType, ProviderType

    env = {
        "time": time,
        "PlaybackState": PlaybackState,
        "PlayerType": PlayerType,
        "MediaType": MediaType,
        "ProviderType": ProviderType,
        "EventType": EventType,
        "PLAYBACK_TARGET_TYPES": {PlayerType.PLAYER},
        "PlayerUnavailableError": ValueError,
        "PlayerCommandFailed": ValueError,
        "get_current_playback_speed": lambda q: 1,
        "get_current_user": lambda: None,
        "utc_timestamp": lambda: 1000,
        "serialize_to_json": json.dumps,
        "cast": cast,
        "DB_TABLE_PLAYLOG": "playlog",
    }
    transfer = method(root, "controllers/player_queues/controller.py", "transfer_queue", env)
    correct = method(root, "controllers/player_queues/controller.py", "on_player_elapsed_time_corrected", env)
    played = method(root, "controllers/music/controller.py", "mark_item_played", env)
    unplayed = method(root, "controllers/music/controller.py", "mark_item_unplayed", env)
    pause = method(root, "providers/spotify/backends/soloist.py", "_observe_external_pause", env)
    cases = []

    for state, ended, resume, expected, kind in [
        (PlaybackState.PLAYING, False, 9, 42, MediaType.TRACK),
        (PlaybackState.PAUSED, False, 77, 77, MediaType.TRACK),
        (PlaybackState.IDLE, False, 31, 31, MediaType.TRACK),
        (PlaybackState.PLAYING, False, 9, 0, MediaType.RADIO),
    ]:
        item = NS(queue_item_id="example-item", queue_id="source", media_type=kind)
        source = NS(
            state=state,
            corrected_elapsed_time=42,
            resume_pos=resume,
            ended=ended,
            current_index=0,
            current_item=item,
            repeat_mode="off",
            shuffle_enabled=False,
            sources=[],
            is_dynamic=False,
        )
        target = NS(state=PlaybackState.IDLE, elapsed_time=999, corrected_elapsed_time=999)
        data = {
            k: NS(
                queue=q,
                items=[item] if k == "source" else [],
                crossfade_override=None,
                autoplay_override=None,
                source_items=[],
                enqueued_media_items=[],
                credited_albums=set(),
            )
            for k, q in [("source", source), ("target", target)]
        }
        player = NS(state=NS(type=PlayerType.PLAYER, active_group=None, synced_to=None))
        controller = NS(
            get=lambda k, data=data: data[k].queue,
            _queue_data=data,
            mass=NS(players=NS(get_player=lambda k, player=player: player), streams=NS(is_smart_fades_active=lambda q: False)),
            _last_played_position=lambda q: 55,
            _resolve_default_toggles=lambda d: None,
            is_smart_shuffle_active=lambda q: False,
            load=AsyncMock(),
            update_items=Mock(),
            index_by_id=lambda *a: 0,
            play_index=AsyncMock(),
            resume=AsyncMock(),
        )

        async def stop(_, source=source):
            source.current_item = None
            source.resume_pos = 0

        controller.stop = stop
        controller._clear = lambda *a, data=data, **kw: data["source"].items.clear()
        await transfer(controller, "source", "target", auto_play=True)
        controller.play_index.assert_awaited_once_with("target", "example-item", expected)
        assert target.current_item is item and item.queue_id == "target"
        cases.append("transfer-" + state.value + "-" + kind.value)

    queue = NS(active=True, elapsed_time=73, flow_mode=False, current_item=None)
    player = NS(type=PlayerType.PLAYER, player_id="example", state=NS(active_source="example", playback_state=PlaybackState.IDLE, corrected_elapsed_time=0))
    signal = Mock()
    controller = NS(get=lambda k: queue, mass=NS(signal_event=signal))
    correct(controller, player)
    assert queue.elapsed_time == 73 and not signal.called
    player.state.playback_state = PlaybackState.PAUSED
    player.state.corrected_elapsed_time = 81
    correct(controller, player)
    assert queue.elapsed_time == 81 and signal.call_count == 1
    cases.append("stopped-position-preserved-paused-position-corrected")

    users = {"source-a": NS(user_id="person-a", provider_filter=["source-a"]), "source-b": NS(user_id="person-b", provider_filter=["source-b"])}
    callbacks = {key: AsyncMock() for key in users}
    tasks, rows, signals = [], [], []
    providers = {key: NS(type=ProviderType.MUSIC, on_played=callbacks[key]) for key in users}
    media = NS(
        item_id="same-book",
        provider="library",
        media_type=MediaType.AUDIOBOOK,
        name="Example book",
        image=None,
        provider_mappings=[NS(provider_instance=k, item_id="same-book") for k in users],
    )
    database = NS(get_row=AsyncMock(return_value=None), delete=AsyncMock(), execute=AsyncMock(), commit=AsyncMock())

    def schedule(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    controller = NS(
        mass=NS(
            webserver=NS(
                auth=NS(
                    get_user=AsyncMock(side_effect=lambda uid: next(u for u in users.values() if u.user_id == uid)),
                    list_users=AsyncMock(return_value=list(users.values())),
                )
            ),
            get_provider=providers.get,
            create_task=schedule,
        ),
        database=database,
        _resolve_playlog_item=AsyncMock(return_value=media),
        _get_user_for_provider=AsyncMock(side_effect=lambda key: users.get(key) if isinstance(key, str) else None),
        _upsert_playlog=AsyncMock(side_effect=lambda params: rows.append(dict(params))),
        _signal_playlog_updated=lambda *a, **kw: signals.append(kw),
        get_controller=lambda _: NS(get_library_item_by_prov_id=AsyncMock(return_value=None)),
    )
    await played(controller, media, fully_played=False, seconds_played=19, provider_instance_id="source-a")
    await played(controller, media, fully_played=False, seconds_played=83, provider_instance_id="source-b")
    assert [(r["userid"], r["seconds_played"]) for r in rows] == [("person-a", 19), ("person-b", 83)]
    assert not tasks  # Provider-origin reports must not echo to either backend account.
    await unplayed(controller, media, provider_instance_id="source-a")
    assert database.delete.await_count == 1 and signals[-1]["userid"] == "person-a"
    await played(controller, media, fully_played=False, seconds_played=41, userid="person-b")
    await asyncio.gather(*tasks)
    callbacks["source-a"].assert_not_awaited()
    callbacks["source-b"].assert_awaited_once()
    cases.append("same-book-two-provider-users-separated-no-progress-echo")
    rows.clear()
    await played(controller, media, fully_played=False, seconds_played=7, provider_instance_id="unknown")
    assert {r["userid"] for r in rows} == {"person-a", "person-b"}
    cases.append("unmapped-upstream-progress-broadcast-observed-household-must-reject")

    stop = AsyncMock()
    tasks.clear()
    run = NS(
        queue_id="example-queue",
        _reader=object(),
        _stopped=False,
        _item_over=False,
        _engine_exited=False,
        _delivery_done=False,
        _error=None,
        spotify_uri="spotify:track:example",
        logger=Mock(),
        mass=NS(create_task=schedule, player_queues=NS(stop=stop)),
    )
    pause(run)
    await asyncio.gather(*tasks)
    stop.assert_awaited_once_with("example-queue")
    for flag in ("_stopped", "_item_over", "_engine_exited", "_delivery_done"):
        stop.reset_mock()
        setattr(run, flag, True)
        pause(run)
        stop.assert_not_called()
        setattr(run, flag, False)
    cases.append("external-pause-stops-only-live-native-run")
    return {
        "official_commit": COMMIT,
        "cases": cases,
        "source_method_execution": True,
        "server_runtime_tested": False,
        "household_connections": False,
        "native_adapter_activated": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(json.dumps(asyncio.run(run(parser.parse_args().source))))
