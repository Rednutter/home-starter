# Offline stand-in for ghcr.io/home-assistant/base-python, used only to
# test-build and run the Home Starter image where the HA registry is not
# reachable. It reproduces the parts of the HA base image the App relies on:
# s6-overlay v3 as /init (same version as home-assistant/docker-base),
# bashio + with-contenv, and CPython 3.13 with pip under /usr/local.
# The distro underneath is Ubuntu (debootstrap) instead of Alpine.
ARG ROOT_IMAGE=local/ubuntu-noble:sim
FROM ${ROOT_IMAGE}
ENV LANG=C.UTF-8 S6_BEHAVIOUR_IF_STAGE2_FAILS=2 S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 S6_CMD_WAIT_FOR_SERVICES=1 S6_SERVICES_READYTIME=50
ADD s6-overlay-noarch.tar.xz s6-overlay-x86_64.tar.xz s6-overlay-symlinks-noarch.tar.xz s6-overlay-symlinks-arch.tar.xz /
COPY bashio/lib /usr/lib/bashio
COPY python /usr/local/python
# Optional extra CA (e.g. a TLS-intercepting egress proxy in the build sandbox).
COPY extra-ca.pem /usr/local/share/extra-ca.pem
ENV PIP_CERT=/usr/local/share/extra-ca.pem
RUN rm -f /usr/local/python/lib/python3.13/EXTERNALLY-MANAGED \
    && ln -s /usr/lib/bashio/bashio /usr/bin/bashio \
    && ln -sf /usr/local/python/bin/python3.13 /usr/local/bin/python3 \
    && ln -sf /usr/local/python/bin/pip3 /usr/local/bin/pip3 \
    && python3 -m pip --version
ENTRYPOINT ["/init"]
