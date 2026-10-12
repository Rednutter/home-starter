# https://developers.home-assistant.io/docs/apps/configuration#app-dockerfile
# Supervisor 2026.04+ no longer injects BUILD_FROM, so the base image is
# explicit (and pinned). The ARG only exists so local test builds can point at
# a mirror of the same image.
ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.13-alpine3.23
FROM ${BUILD_FROM}

ARG BUILD_VERSION=0.2.0

COPY server/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY rootfs /
COPY server/homestarter /opt/homestarter/homestarter

RUN chmod a+x /etc/services.d/home-starter/run /etc/services.d/home-starter/finish

ENV PYTHONPATH=/opt/homestarter \
    PYTHONUNBUFFERED=1 \
    HOME_STARTER_VERSION=${BUILD_VERSION}

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    io.hass.name="Home Starter" \
    io.hass.description="Scan Home Assistant and set up useful outcomes." \
    io.hass.url="https://github.com/Rednutter/home-starter" \
    org.opencontainers.image.title="Home Assistant App: Home Starter" \
    org.opencontainers.image.description="Scan Home Assistant and set up useful outcomes." \
    org.opencontainers.image.source="https://github.com/Rednutter/home-starter" \
    org.opencontainers.image.licenses="MIT"
