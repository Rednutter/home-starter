#!/usr/bin/env bash
# Build the offline base-image stand-in, then the real Home Starter image on it.
#   devtools/container-sim/build.sh <dir with s6 tarballs + bashio checkout> <python3.13 install dir>
# The Ubuntu root image must exist first:
#   debootstrap --variant=minbase --include=bash,jq,tzdata,curl,ca-certificates,xz-utils noble rootfs http://archive.ubuntu.com/ubuntu
#   tar -C rootfs -c . | docker import - local/ubuntu-noble:sim
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dl="$1"; py="$2"
ctx="$(mktemp -d)"
trap 'rm -rf "$ctx"' EXIT
cp "$here/Dockerfile" "$ctx/"
cp "$dl"/s6-overlay-*.tar.xz "$ctx/"
cp -r "$dl/bashio" "$ctx/bashio"
cp -r "$py" "$ctx/python"
# Trust store for pip inside the build: the system bundle, or CA_BUNDLE if set.
cp "${CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}" "$ctx/extra-ca.pem"
docker build -q -t local/ha-base-python-sim:3.13 "$ctx"
# --network host + HTTPS_PROXY (a predefined build arg) only matter in
# sandboxes where the network is reachable solely through a local proxy.
docker build --network host --build-arg HTTPS_PROXY="${HTTPS_PROXY:-}" \
  -t local/home-starter:0.1.0 \
  --build-arg BUILD_FROM=local/ha-base-python-sim:3.13 \
  --build-arg BUILD_VERSION=0.1.0 \
  "$here/../../home_starter"
