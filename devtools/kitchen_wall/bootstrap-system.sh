#!/bin/sh
# Run once as root after reviewing this file. No credentials or reboot are involved.
set -eu
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this script with sudo in your own terminal.' >&2
    exit 1
fi
: "${SUDO_USER:?Run through sudo from the display account}"
# Runtime libraries missing from the inspected Pi; headers support upstream voice wheels.
apt-get update
apt-get install --no-install-recommends -y ddcutil i2c-tools libmpv2 libportaudio2 libasound2-dev python3-dev build-essential cmake pkg-config
# Keep user audio/health services running independently of the graphical session.
loginctl enable-linger "$SUDO_USER"
printf '\nHome Starter system dependencies ready. No reboot or account permission changes made.\n'
