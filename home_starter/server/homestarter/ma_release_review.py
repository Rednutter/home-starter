"""Uninstalled 2.10.8 native candidate. Never imported by automatic startup.

Explicit native installation/activation needs separate review and approval.
No account, token, provider filter or persistent permission is created here.
Public controls use MA APIs; only enforcement and finite transfer retain private
dependencies, bound to exact reviewed source and live wrapper identities.
"""

import hashlib
import inspect
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .ma_control_contract import CANDIDATE_ID, FEATURES

# Exact official public source hashes; not credentials.
PINS = {  # pragma: allowlist secret
    "mass.py": "8c9baf664fa86cf1584635fc5a4879333c01a9981be3460cbfcdcf142c92a40e",  # pragma: allowlist secret
    "controllers/streams/audio.py": "30df90fa3915db99d8bf78eb390d6a872601bf058b26837dae686902a6f9199b",  # pragma: allowlist secret
    "providers/spotify/backends/soloist.py": "b9862f993f114f8e5d8286c856e6e22bbefa9a610f83e5a2f68e81618dc4dbcf",  # pragma: allowlist secret
    "controllers/player_queues/controller.py": "cdf5f0de4ce8294576999cdb5ad31a73077a431584b131ed22765ddd4fa76bef",  # pragma: allowlist secret
    "controllers/player_queues/queue_loader.py": "7f23e5c1d613ad7529a9c691ffe22f1cd32019490f622f6a3f5f6ea40d2be11c",  # pragma: allowlist secret
    "controllers/player_queues/helpers.py": "98ca6e1235eb132ad643fd872695497ae3b5290a2e356c566c18c087be14d000",  # pragma: allowlist secret
    "controllers/player_queues/state.py": "53d9da3ec76dfdc6ce57eee33ae64b5307dde405eb5347ebefa54644e4350a35",  # pragma: allowlist secret
    "controllers/players/controller.py": "2e39fe47e208dfa566d2dfcca253f7e1dab81f0f05bd35ba21c5e7f451439564",  # pragma: allowlist secret
}
ANCHOR = "        self._register_api_commands()\n"
HOOK = ANCHOR + "        from home_starter_ma.ma_release_review import install as install_household_candidate\n        install_household_candidate(self)\n"


def source_verified(root, release, models):
    if release != "2.10.8" or models != "1.1.205":
        return False
    try:
        for name, digest in PINS.items():
            body = (Path(root) / name).read_bytes()
            if name == "mass.py" and body.count(HOOK.encode()) == 1:
                body = body.replace(HOOK.encode(), ANCHOR.encode())
            if hashlib.sha256(body).hexdigest() != digest:
                return False
        return True
    except OSError:
        return False


class ReviewedRelease:
    def __init__(self, mass):
        self.mass = mass
        self.root = Path(inspect.getsourcefile(type(mass))).resolve().parent

    def valid(self):
        try:
            if not source_verified(self.root, self.mass.version, version("music-assistant-models")):
                return False
            audio = self.mass.streams.audio
            functions = [
                (getattr(audio, name), "controllers/streams/audio.py")
                for name in ("get_stream_details", "get_audio_buffer", "_get_mapping_providers", "_discover_alternative_provider_mappings", "get_media_stream")
            ]
            functions += [
                (self.mass.player_queues.transfer_queue, "controllers/player_queues/controller.py"),
                (self.mass.players.get_group_and_player_lock, "controllers/players/controller.py"),
            ]
            guard = getattr(self.mass, "home_starter_account_guard", None)
            if guard is not None and guard.soloist_class is not None:
                functions.append((guard.soloist_class._acquire_run, "providers/spotify/backends/soloist.py"))
            return all(Path(inspect.getsourcefile(inspect.unwrap(fn))).resolve() == self.root / name for fn, name in functions)
        except (OSError, TypeError, AttributeError, PackageNotFoundError):
            return False


def install(mass):
    """Explicit new-candidate operator entry; refuses replacing a running guard."""
    from music_assistant_models.auth import Scope

    from .ma_account_guard import install as install_guard
    from .ma_transfer import NativeTransfers, register

    review = ReviewedRelease(mass)
    if not review.valid() or getattr(mass, "home_starter_account_guard", None):
        raise RuntimeError("Candidate source/runtime needs review; no commands installed.")
    guard = install_guard(mass, review=review)
    transfers = NativeTransfers(mass, review=review)
    if not transfers.source_origin_ok:
        raise RuntimeError("Candidate transfer origin changed; startup stopped safely.")
    register(mass, transfers)

    async def status():
        verified = review.valid()
        account = verified and (await guard.status())["isolated"]
        transfer = verified and (await transfers.status())["pinned"]
        return {
            "protocol": 1,
            "version": mass.version,
            "review": CANDIDATE_ID,
            "source_verified": verified,
            "features": {name: bool(account and (transfer if name == "finite_transfer" else True)) for name in FEATURES},
        }

    mass.register_api_command("homestarter/compatibility_status", status, required_scope=Scope.USERS_MANAGE)
    return guard
