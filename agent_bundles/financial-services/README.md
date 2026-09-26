# Financial Services Agent Bundle

Curated marketplace agents copied from the local Claude Financial Services
marketplace install:

`/Users/mz/.claude/plugins/marketplaces/claude-for-financial-services/plugins/agent-plugins/`

The canonical marketplace prompt body is preserved in each file. Cross-host
installation renders these agents with an `aa_` namespace so our managed copies
do not collide with Claude plugin-provided agents.

Review status:

- Imported as a central bundle for Claude, Codex, Gemini, and Anvil sync.
- Needs a dedicated agnostic-review pass for host tool references such as Claude
  MCP tool names before being considered fully portable.
