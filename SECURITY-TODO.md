# SECURITY-TODO — global, agent-agnostic

> Tracks security-control gaps that need to be fixed in the agent infrastructure itself, not in any one project.
> Synced to all hosts via `scripts/sync_prompt_pack.py`.

## P0 — output redaction hook (TRACKED, NOT BUILT)

**Problem:** Agents leak sensitive infrastructure values in conversation transcripts via Bash tool stdout. This has happened 3+ times in a single session despite the agent reading a "never expose secrets" lesson at session start. Behavioral rules are not enough — the agent rationalizes its way past them.

**Required control:** A `PostToolUse` hook on the `Bash` tool that scans command output BEFORE it returns to the agent's context and redacts known-sensitive patterns inline. Replaces the value with a category marker (e.g. `[REDACTED:IPv4]`, `[REDACTED:SSH_PATH]`, `[REDACTED:PAT]`) so the agent can still reason about WHAT was returned without seeing the value.

**Scope (global, not per-project):** Lives at `~/.claude/hooks/output-redact.js` and equivalent paths for codex/gemini/anvil. Wired in `~/.claude/settings.json` under `PostToolUse` matching `Bash`. Synced via the existing prompt-pack pipeline so every host gets it.

**Patterns to redact (initial set):**

- IPv4 addresses outside well-known private ranges (10.*, 172.16-31.*, 192.168.*, 127.*)
- IPv6 globally-routable addresses
- Server filesystem paths matching common hosting patterns (Cloudways `/home/<digits>.cloudwaysapps.com/.../public_html`, AWS `/var/app/`, etc.)
- Hostnames matching `*.cloudwaysapps.com`, `*.amazonaws.com` instance hostnames, etc.
- GitHub tokens: `gh[oprs]u_[A-Za-z0-9]{36,}`
- AWS access keys: `AKIA[0-9A-Z]{16}`
- Cloudflare API tokens
- Slack tokens: `xox[bpoarsu]-...`
- Stripe keys: `sk_(test|live)_...`, `pk_(test|live)_...`
- Generic 32+ character base64 / hex tokens on lines containing `Authorization`, `Bearer`, `token`, `password`, `secret`, `key`
- SSH usernames matching `*_automation`, `*_staging`, `*_prod` patterns
- Private key headers: `-----BEGIN (RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY`

**Behavior:**

- Default: redact inline. Output reaches agent with values replaced by category markers.
- Bypass mechanism: agent can set `CLAUDE_HOOK_REDACT=skip` for a single command IF AND ONLY IF the user has explicitly approved that bypass in conversation. Bypass uses are logged to `~/.claude/security-bypass.log` for audit.
- Allowlist: per-project `.claude-redact-allow` file can whitelist patterns that are project-specific safe-to-show (e.g. test fixture IPs).

**Why behavior-only rules don't work:**

- The agent reads the lesson at session start.
- During work, the agent forms rationalizations ("this one is fine because X").
- Rationalization fires before output review.
- The output lands in transcript.
- The lesson is reinforced.
- Next session, same loop.

A mechanical filter on tool output breaks the loop because the agent never sees the raw value to rationalize about. Redaction happens at the harness layer, below the agent's reasoning.

**Acceptance criteria:**

- Hook file written, executable, tested against synthetic input with each pattern.
- Wired in `~/.claude/settings.json` PostToolUse matcher.
- Same hook synced to `~/.codex/hooks/`, `~/.gemini/hooks/`, `/opt/anvil/hooks/` via prompt-pack sync.
- Reference test fixture in `~/_CODING/autonomous_agents_mds/tests/output-redact-fixtures.txt` covering each pattern category.
- Documented in agent `CLAUDE.md` so the agent knows redaction is happening (so it doesn't get confused by `[REDACTED:*]` markers in tool output).
- One-paragraph entry in the global "Active Lessons" memory pointing at this control as the prevention mechanism, replacing the current "never echo secrets" behavioral rule which has demonstrably failed.

**Out of scope for now (next iteration):**

- Redaction of agent-authored response text (not just tool output). Harder — requires a different hook point. Tool output is the dominant leak vector; covering it first.
- Encrypting `~/.claude/security-bypass.log` with the user's key.
- ML-based pattern detection. Start with regex; iterate.

## Status

Status: **BUILT 2026-06-12 — claude host only**.
Hook: `/Users/mz/_CODING/hooks/output-redact/output-redact.js` (symlinked to `~/.claude/hooks/output-redact.js`)
Tests: 27/27 passing — `/Users/mz/_CODING/hooks/output-redact/test/run-tests.sh`
Wired in: `~/.claude/settings.json` `hooks.PostToolUse.matcher=Bash`.

## Remaining work

- [ ] Sync hook to `~/.codex/hooks/`, `~/.gemini/hooks/`, `/opt/anvil/hooks/`. Update `scripts/sync_prompt_pack.py` to copy `output-redact.js` to each host's hooks dir and wire into each host's settings/config equivalent.
- [ ] Add an entry to global Active Lessons memory pointing at this control (replaces the failing behavioral lesson #2 as the primary mitigation).
- [ ] Document the `CLAUDE_HOOK_REDACT_BYPASS=1` escape hatch in `~/.claude/CLAUDE.md` so future agents know it exists.
- [ ] Audit log location: `~/.claude/security-bypass.log` — add to weekly review.

## Outstanding rotation items

- [ ] **metazen11 GitHub PAT** — leaked 2026-06-12 via `gh auth git-credential get` output (before this hook existed). Revoke at https://github.com/settings/tokens. The leaked PAT predates the redaction hook so no automatic protection applied. After rotation, this entry can be closed.
