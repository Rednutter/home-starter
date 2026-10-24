"""Linux-only, disposable MA startup checks; never physical playback acceptance.

Run inside the digest-pinned image with --network none, no credentials/devices,
read-only root and ephemeral /data and /tmp. Output only fixed check labels.
"""

import argparse
import asyncio
import importlib.metadata
import logging
import os
import socket
from pathlib import Path


def verify_isolation():
    if os.name != "posix" or not Path("/.dockerenv").exists():
        raise RuntimeError("Requires the isolated Linux test container")
    if set(os.listdir("/sys/class/net")) != {"lo"}:
        raise RuntimeError("Requires network-none with loopback only")
    if importlib.metadata.version("music_assistant") != "2.10.8":
        raise RuntimeError("Unexpected MA version")
    if importlib.metadata.version("music-assistant-models") != "1.1.205":
        raise RuntimeError("Unexpected models version")
    if Path("/data/settings.json").exists():
        raise RuntimeError("Requires empty disposable data")


async def check(candidate):
    verify_isolation()
    from music_assistant.mass import MusicAssistant

    logging.disable(logging.CRITICAL)
    mass = MusicAssistant("/data", "/data/cache", safe_mode=True)
    try:
        await asyncio.wait_for(mass.start(), timeout=90)
        assert mass.version == "2.10.8"
        assert all(provider.manifest.builtin for provider in mass.providers)
        assert not any(provider.domain == "spotify" for provider in mass.providers)
        info = mass.get_server_info()
        assert info.server_version == "2.10.8"
        # Exercise the real webserver inside this container only. No host port.
        import aiohttp

        async with aiohttp.ClientSession() as client:
            async with client.get("http://127.0.0.1:8095/info", timeout=aiohttp.ClientTimeout(total=5)) as response:
                assert response.status == 200
                assert (await response.json())["server_version"] == "2.10.8"
        print("PASS real safe-mode startup and loopback info", flush=True)
        command = "homestarter/compatibility_status"
        if candidate:
            from home_starter_ma.ma_release_review import ReviewedRelease
            from home_starter_ma.spotify_leases import AccountsBusy

            assert ReviewedRelease(mass).valid()
            assert command in mass.command_handlers
            guard = mass.home_starter_account_guard
            assert not guard.identities
            try:
                await guard.engine.reserve(guard.providers(), "synthetic-room", "synthetic-session", "House")
            except AccountsBusy:
                pass
            else:
                raise AssertionError("Empty Spotify mapping unexpectedly allocated an account")
            print("PASS candidate source origins, registration and fail-closed provider absence", flush=True)
        else:
            assert command not in mass.command_handlers
            assert not hasattr(mass, "home_starter_account_guard")
            print("PASS official baseline has no household adapter", flush=True)
    finally:
        await asyncio.wait_for(mass.stop(), timeout=30)
        print("PASS bounded shutdown", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    # Guard against accidental DNS use by test code; network-none is the actual
    # isolation boundary and also applies to subprocesses/native dependencies.
    socket.setdefaulttimeout(5)
    try:
        asyncio.run(check(args.candidate))
    except Exception as exc:
        print("FAIL isolated MA runtime: " + type(exc).__name__, flush=True)
        raise SystemExit(1) from None
