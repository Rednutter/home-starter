#!/bin/sh
# HAOS host-console operator tool. No MA update/start/restart, network changes,
# Docker socket mount, data mount or production write in check/prepare modes.
set -eu
umask 077
MODE=check
if [ "${1:-}" = --prepare ]; then MODE=prepare; shift; fi
if [ "${1:-}" = --apply ]; then MODE=apply; shift; fi
if [ "$#" -ne 8 ]; then
    echo 'Usage: sh stage_ma2108_offline.sh [--prepare|--apply] CONTAINER PINNED_IMAGE BUNDLE NEW_WORK BACKUP RECEIPT ROLLBACK_IMAGE SUPERVISOR_VERSION' >&2
    exit 64
fi
TARGET=$1 IMAGE=$2 BUNDLE=$3 WORK=$4 BACKUP=$5 RECEIPT=$6 ROLLBACK=$7 SUPERVISOR=$8
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
fail() { echo "$1" >&2; exit 1; }
stopped() {
    [ "$(docker inspect --format '{{.State.Running}} {{.State.Paused}} {{.State.Restarting}}' "$TARGET")" = 'false false false' ] || fail 'Target must remain stopped; no write/start attempted'
    [ "$(docker inspect --format '{{.Image}}' "$TARGET")" = "$IMAGE_ID" ] || fail 'Target image changed'
    case "$(docker inspect --format '{{.State.Status}}' "$TARGET")" in created|exited) ;; *) fail 'Target state is not created/exited' ;; esac
}
case "$TARGET" in app_d5369777_music_assistant|hs-ma2108-ci-target-*) ;; *) fail 'Unexpected target container name' ;; esac
case "$IMAGE" in
    ghcr.io/music-assistant/server@sha256:2a0536321d0554d6157504e8e477ef871dd41d466bdc22f250ccaff19f667e58) ;; # pragma: allowlist secret -- public amd64 image
    ghcr.io/music-assistant/server@sha256:0b94830c8ddb2347cfdc6993adc4c586ef4945fdbb490698ab9e01d1ba25adbb) ;; # pragma: allowlist secret -- public arm64 image
    *) fail 'Only exact reviewed official MA 2.10.8 images are accepted' ;;
esac
case "$WORK" in /tmp/hs-ma2108-*|/mnt/data/supervisor/share/hs-ma2108-*) ;; *) fail 'Choose a dedicated absolute hs-ma2108 work path' ;; esac
case "$WORK" in *[!a-zA-Z0-9_./-]*) fail 'Work path contains unsupported characters' ;; esac
[ ! -e "$WORK" ] || fail 'Work path exists; inspect uncertain prior outcome instead of replaying'
[ "$(readlink -f "$(dirname "$WORK")")/$(basename "$WORK")" = "$WORK" ] || fail 'Work parent is not canonical'
[ -s "$BUNDLE" ] && [ -s "$BACKUP" ] && [ -s "$RECEIPT" ] || fail 'Archive, backup and receipt must exist'
[ "${DOCKER_HOST:-unix:///var/run/docker.sock}" = unix:///var/run/docker.sock ] || fail 'Only the existing local Docker socket is supported'
[ "$(docker context inspect --format '{{.Endpoints.docker.Host}}')" = unix:///var/run/docker.sock ] || fail 'Remote Docker context refused'
IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
[ "$IMAGE_ID" = "$(docker inspect --format '{{.Image}}' "$TARGET")" ] || fail 'Target is not the exact reviewed image'
[ -n "$(docker image inspect --format '{{.Id}}' "$ROLLBACK")" ] || fail 'Rollback image is not locally available'
case "$ROLLBACK" in sha256:*|ghcr.io/music-assistant/server@sha256:*) ;; *) fail 'Rollback image must have an immutable identity' ;; esac
docker run --rm --network none --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --entrypoint /app/venv/bin/python "$ROLLBACK" -c 'from importlib.metadata import version; assert version("music_assistant")=="2.10.7"' || fail 'Rollback image is not MA 2.10.7'
stopped
mkdir "$WORK"
cp "$BUNDLE" "$WORK/candidate.tar"
cp "$RECEIPT" "$WORK/receipt.json"
cp "$HERE/ma2108_offline_payload.py" "$WORK/payload.py"
BACKUP_SUM=$(sha256sum "$BACKUP") || fail 'Backup checksum read failed'
BACKUP_SHA=${BACKUP_SUM%% *}
helper() {
    docker run --rm --network none --read-only --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --memory 1g --cpus 1 --tmpfs /tmp:rw,mode=1777 --mount "type=bind,src=$WORK,dst=/work" --entrypoint /app/venv/bin/python "$IMAGE" "$@"
}
helper /work/payload.py receipt --backup-sha "$BACKUP_SHA" --rollback-image "$ROLLBACK"
ROOT=$(helper -c 'import importlib.util; from pathlib import Path; p=Path(importlib.util.find_spec("music_assistant").origin).parent; assert str(p).startswith("/app/") and p.name=="music_assistant"; print(p)')
case "$ROOT" in /app/*/music_assistant|/app/music_assistant) ;; *) fail 'Unrecognised package location' ;; esac
printf '%s\n' "$ROOT" > "$WORK/package-root.txt"
CODE=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --unix-socket /var/run/docker.sock --head "http://localhost/containers/$TARGET/archive?path=$(dirname "$ROOT")/home_starter_ma")
[ "$CODE" = 404 ] || fail 'Adapter directory exists or absence could not be established; reconcile before overwrite'
# Copy only eight pinned public source files, never /data or configuration.
for FILE in mass.py controllers/streams/audio.py providers/spotify/backends/soloist.py controllers/player_queues/controller.py controllers/player_queues/queue_loader.py controllers/player_queues/helpers.py controllers/player_queues/state.py controllers/players/controller.py; do
    stopped
    mkdir -p "$WORK/original/music_assistant/$(dirname "$FILE")"
    docker cp "$TARGET:$ROOT/$FILE" "$WORK/original/music_assistant/$FILE"
done
if [ "$MODE" = check ]; then
    helper /work/payload.py check
    echo 'CHECK ONLY: target unchanged. Supervisor lifecycle/native activation remain gated.'
    exit 0
fi
helper /work/payload.py prepare
if [ "$MODE" = prepare ]; then
    echo 'PREPARED OFFLINE ONLY: target unchanged; no MA service started.'
    exit 0
fi
# No reviewed Supervisor version is currently enabled. This must refuse before
# the first target write; passing source checks is not update-lifecycle evidence.
helper /work/payload.py gate --supervisor-version "$SUPERVISOR"
stopped
echo 'modules-copy-pending' > "$WORK/journal"
docker cp "$WORK/original/home_starter_ma" "$TARGET:$(dirname "$ROOT")/home_starter_ma"
stopped
echo 'source-backup-copy-pending' > "$WORK/journal"
docker cp "$WORK/original/music_assistant/mass.home-starter-2108-original" "$TARGET:$ROOT/mass.home-starter-2108-original"
stopped
echo 'startup-copy-pending' > "$WORK/journal"
docker cp "$WORK/original/music_assistant/mass.py" "$TARGET:$ROOT/mass.py"
stopped
for FILE in mass.py controllers/streams/audio.py providers/spotify/backends/soloist.py controllers/player_queues/controller.py controllers/player_queues/queue_loader.py controllers/player_queues/helpers.py controllers/player_queues/state.py controllers/players/controller.py; do
    stopped
    mkdir -p "$WORK/readback/music_assistant/$(dirname "$FILE")"
    docker cp "$TARGET:$ROOT/$FILE" "$WORK/readback/music_assistant/$FILE"
done
docker cp "$TARGET:$(dirname "$ROOT")/home_starter_ma" "$WORK/readback/home_starter_ma"
docker cp "$TARGET:$ROOT/mass.home-starter-2108-original" "$WORK/readback/music_assistant/mass.home-starter-2108-original"
helper /work/payload.py verify
stopped
echo 'staged-not-started' > "$WORK/journal"
echo 'Source staged; MA remains stopped. No update/start/restart was issued.'
