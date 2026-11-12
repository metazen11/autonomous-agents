#!/bin/bash
# Long-lived container: virtual display -> VNC (container-local only) -> noVNC on 6080.
# Work runs via `docker exec` (see tools/visible-vm/vm).
set -e
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
for _ in $(seq 1 50); do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.1; done
[ -e /tmp/.X11-unix/X99 ] || { echo "Xvfb did not start" >&2; exit 1; }
x11vnc -display :99 -nopw -localhost -forever -shared -quiet &
websockify --web /usr/share/novnc 6080 localhost:5900 &
exec sleep infinity
