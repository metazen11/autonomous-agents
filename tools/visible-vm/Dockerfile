# Headed-browser VM: Playwright image + virtual display + noVNC.
# Build: docker build --build-arg PW_VERSION=1.58.2 -t visible-vm:1.58.2 tools/visible-vm
# Pin PW_VERSION to the project's @playwright/test version (lockfile).
ARG PW_VERSION=1.58.2
FROM mcr.microsoft.com/playwright:v${PW_VERSION}-noble
# Extension point: extra apt packages for a project (space-separated).
ARG EXTRA_APT=""
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify socat jq curl git perl ${EXTRA_APT} \
 && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /usr/local/bin/vm-entrypoint
RUN chmod +x /usr/local/bin/vm-entrypoint
ENV DISPLAY=:99
ENTRYPOINT ["/usr/local/bin/vm-entrypoint"]
