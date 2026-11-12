# Runbook: QA UI (headed browser work)

Used by the `qa-ui` agent (`agent_bundles/anvil-local/agents/qa-ui.md`, installed as
`aa_qa_ui`) and anything that inherits it (`anvil-qa-ui`). Browser mechanics live in the
`visible-vm` skill (`skills/visible-vm/skill.md`, tool `tools/visible-vm/vm`).

## 1. Spot check or test?

| | MCP spot check | Deterministic Playwright test |
|---|---|---|
| Runs via | MCP attached to `vm browser` (CDP) | `vm run -- <suite cmd>` |
| Use for | Exploratory verification of a fresh change; reproducing a reported bug; visual/judgment checks; one-off post-deploy confirmation | Any acceptance criterion; a regression that happened once; a gate (PR/release); a flow checked more than twice |
| Output | Evidence: screenshots, console errors, network. Not a test. | Pass/fail per spec + JSON report |

Rule of thumb: if you spot-checked the same thing twice, or a bug escaped, promote it to a test.

### Promotion procedure (spot check -> spec)

1. Write the spot-check steps down as a spec.
2. Selectors: stable `data-*` attributes / roles over visible text or CSS structure.
3. Waits: explicit waits on app state (`expect(...)`, `waitForFunction`), never sleeps.
4. No live-data assumptions: seed or read current state from the API/DOM; no hardcoded counts or names.
5. Assert content-type and state, not just HTTP 200 (a dead host can return 200 + an HTML error page).
6. For a bug fix: run the spec against the UNFIXED code and see it fail for the right reason, then pass with the fix.
7. Add it to the suite and to the gate (smoke and/or full scope) in the same change.

## 2. Bootstrapping QA UI in a repo

1. Detect an existing Playwright config/tests (`playwright.config.*`, `tests/`, `e2e/`) and
   REUSE them. Only add the minimum below when nothing exists.
2. Minimal layout:
   - `playwright.config.ts` with headed opt-in: `use: { headless: !process.env.PLAYWRIGHT_HEADED }`.
   - `tests/qa-ui/` with one smoke spec (page loads, key element present, no unexpected console errors).
   - A runner script (`tests/qa-ui/run-qa.sh`) with `--smoke` and full scopes that writes a JSON report
     (`tests/qa-ui/results/qa-report.json`).
3. Lanes, same command in both:
   - Local: `vm up --pw-version <V>` then `vm run -- tests/qa-ui/run-qa.sh --smoke`.
   - CI: `xvfb-run -a tests/qa-ui/run-qa.sh --smoke` (headed on Xvfb, `PLAYWRIGHT_HEADED=1`).
4. Pin the image to the repo's lockfile Playwright version (`vm up --pw-version <V>`); a
   mismatched browser build makes Playwright refuse to launch.
5. The repo needs `jq curl perl git` if its runner uses them; they are in the image. Anything else:
   build with `--build-arg EXTRA_APT=...`.

## 3. Operator visibility

- Always hand the operator the noVNC watch URL printed by `vm up` / `vm browser`
  (`http://127.0.0.1:6080/vnc.html?autoconnect=1`, or the `VM_NOVNC_PORT` override).
- Never run a headed browser on the host. Never publish ports beyond loopback.

## 4. Reporting

- Per-check PASS/FAIL, each with evidence (screenshot path, console/network excerpt, assertion).
- Separate environment failures from product failures: check `uptime` (swiftshader is
  CPU-bound; high load fails identically on any engine), server reachability, and image/Playwright
  version match BEFORE calling something a regression. Re-run an env-suspect failure once on a quiet
  machine; do not retry silently.
- A skipped or not-run suite is reported as skipped/NOT RUN, never as pass. Zero specs executed
  is a FAIL, not a clean pass.
- Include the watch URL, the exact command run, and the report path in the result.
