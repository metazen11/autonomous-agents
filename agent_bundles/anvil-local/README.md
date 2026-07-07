# Anvil Local Agent Bundle

Curated agents imported from `/Users/mz/_CODING/anvil/agents/` during the
cross-host prompt-pack reconciliation work.

These are tracked here so Claude, Codex, Gemini, and Anvil can share a central
inventory. Agents in this bundle are installed with the `aa_` namespace by
`scripts/sync_prompt_pack.py` to avoid collisions with host-native or plugin
agents.

Review status:

- `anvil-qa.md` and `anvil-qa-ui.md` are Anvil-specific and should stay in this
  bundle unless rewritten as fully host-agnostic QA contracts.
- `dev.md`, `docs.md`, `pm.md`, `pr.md`, `qa-ui.md`, and `report.md` are likely
  candidates to graduate into first-party `agents/` after a dedicated
  agnostic-review pass.
