---
name: visible-vm
description: "Run headed browser/UI work (Playwright suites or MCP browsing) inside a container on a virtual display the operator can watch via noVNC, so no windows open on the operator's machine. Wraps tools/visible-vm/vm."
argument-hint: "up | run -- <cmd> | browser | watch | status | down"
user-invocable: true
---

# /visible-vm — headed browsers in a watchable container

Use for ANY headed browser or UI test, or agent browsing, that would otherwise open
windows on the operator's machine. Never launch a headed browser on the host.

CLI: `tools/visible-vm/vm` (bash 3.2 compatible). Subcommands accept `--project DIR`
(default `$PWD`). Ports: `VM_NOVNC_PORT` (6080), `VM_CDP_PORT` (9222) for multiple projects.

## Start and hand over the watch URL

```bash
tools/visible-vm/vm up --project <repo>      # builds visible-vm:<pw-version> once (~4 GB)
# prints: watch: http://127.0.0.1:6080/vnc.html?autoconnect=1  -> always give this to the operator
```

Pin the image to the repo's Playwright version: `vm up --pw-version <lockfile version>`
(or `VM_PW_VERSION`). The project dir is mounted at the same path; `node_modules` lives in a
per-project Linux named volume (host `node_modules` is never used).

## Deterministic suites (acceptance criteria, regressions, gates)

```bash
tools/visible-vm/vm run --env API_TOKEN -- npx playwright test tests/qa-ui
```

Runs with `DISPLAY=:99` and `PLAYWRIGHT_HEADED=1`. Deps install via `npm ci` once per
`package-lock.json` checksum. `--env NAME` forwards by name only; values are never echoed.
Configs must honour `PLAYWRIGHT_HEADED` (`use: { headless: !process.env.PLAYWRIGHT_HEADED }`).

## Exploratory / debug browsing (MCP attached over CDP)

```bash
tools/visible-vm/vm browser   # persistent headed Chromium; CDP at http://127.0.0.1:9222
```

Flags verified against `--help` (2026-11): Playwright MCP `--cdp-endpoint <endpoint>`,
Chrome DevTools MCP `--browserUrl` (`-u`). Paste-ready snippet (do NOT auto-apply; the
operator decides where it goes):

```json
{
  "mcpServers": {
    "playwright-vm": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--cdp-endpoint", "http://127.0.0.1:9222"]
    },
    "chrome-devtools-vm": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest", "--browserUrl", "http://127.0.0.1:9222"]
    }
  }
}
```

Use one MCP at a time against the same browser. Pages the MCP opens are visible on the
noVNC display.

## Gotchas

- **Load.** Docker Desktop needs enough CPU/memory (Settings > Resources). Chromium on the
  virtual display uses swiftshader (pure-CPU WebGL) and is load-sensitive: check `uptime`
  before reading a failure as a product regression.
- **Local dev servers** on the host are reachable as `http://host.docker.internal:<port>`,
  not `localhost`.
- **node_modules** are Linux binaries in the volume; do not expect host installs to work in
  the container or vice versa. Reset: `docker volume rm visible-vm-nm-<hash>` (hash is in `vm status`).
- **Never bind beyond loopback.** `vm` publishes only on loopback; do not edit it to widen.
  VNC has no password (`-nopw`), safe only because of that.
- **Worktrees.** A git worktree's `.git` file points at a host path that does not exist in
  the container, so git commands inside may fail. Pass SHAs/branch names via env instead.
- **Chromium CDP** binds container-loopback only; `vm browser` uses a socat relay
  (9223 -> 9222). `--remote-debugging-address` is ignored by recent Chromium.
- Extra system packages: `docker build --build-arg EXTRA_APT="pkg1 pkg2" ...` (`vm up` builds
  with defaults; pre-build the tag yourself if you need extras).

## Teardown

`tools/visible-vm/vm down --project <repo>` removes the container; the node_modules volume is kept.

See `docs/runbooks/qa-ui.md` for when to use MCP vs a Playwright suite.
