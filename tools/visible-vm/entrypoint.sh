#!/bin/bash
# Long-lived container: virtual display -> VNC (container-local only) -> noVNC on 6080.
# Work runs via `docker exec` (see tools/visible-vm/vm).
set -e
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
for _ in $(seq 1 50); do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.1; done
[ -e /tmp/.X11-unix/X99 ] || { echo "Xvfb did not start" >&2; exit 1; }
x11vnc -display :99 -nopw -localhost -forever -shared -quiet &
# Origin allow-list: a web page open in the host browser can otherwise reach this
# password-less VNC via ws://127.0.0.1 (browsers do not CORS-check WebSockets).
websockify --web /usr/share/novnc \
  --auth-plugin ExpectOrigin --auth-source "${VM_ALLOWED_ORIGINS:?set by vm up}" \
  6080 localhost:5900 &
# Exit (container stops, vm status says so) as soon as any child dies.
wait -n
exit 1
