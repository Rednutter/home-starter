"""Separate read compatibility from explicitly installed native control contracts."""

import time

CANDIDATE_ID = "ma2108-contract-1"
FEATURES = {"transport", "queue", "groups", "finite_transfer", "spotify"}


def check_progress_start(endpoint, kind):
    if isinstance(endpoint, dict) and endpoint.get("version") == "2.10.8" and kind in {"audiobook", "podcast_episode"}:
        raise ValueError("Book and podcast progress routing needs review for MA 2.10.8. No playback was started.")


def attestation(value, endpoint):
    """Only call on a response from the bound, authenticated MA connection."""
    if (
        not isinstance(value, dict)
        or type(value.get("protocol")) is not int
        or value.get("protocol") != 1
        or value.get("version") != "2.10.8"
        or endpoint.get("version") != "2.10.8"
        or value.get("review") != CANDIDATE_ID
        or value.get("source_verified") is not True
        or not isinstance(value.get("features"), dict)
        or set(value["features"]) != FEATURES
        or any(type(v) is not bool for v in value["features"].values())
        or any(not isinstance(endpoint.get(k), str) or not endpoint[k] for k in ("server_id", "app"))
    ):
        return None
    return {
        "review": CANDIDATE_ID,
        "server_id": endpoint["server_id"],
        "app": endpoint["app"],
        "features": dict(value["features"]),
        "expires": time.monotonic() + 5,
    }


def supports(endpoint, feature):
    if not isinstance(endpoint, dict) or feature not in FEATURES:
        return False
    if endpoint.get("version") == "2.10.7":
        return True  # Preserve the existing reviewed baseline and its downstream guards.
    proof = endpoint.get("_native_review")
    return bool(
        endpoint.get("version") == "2.10.8"
        and feature in FEATURES
        and isinstance(proof, dict)
        and proof.get("review") == CANDIDATE_ID
        and proof.get("server_id") == endpoint.get("server_id")
        and proof.get("app") == endpoint.get("app")
        and type(proof.get("expires")) in {float, int}
        and time.monotonic() < proof["expires"] <= time.monotonic() + 5
        and proof.get("features", {}).get(feature) is True
    )
