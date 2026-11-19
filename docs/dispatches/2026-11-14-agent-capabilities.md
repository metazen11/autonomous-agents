# Agent capability and skill security remediation

Operator asks to bridge actual agent-role gaps, require senior engineering or domain-specialist standards, make necessary skills available, and audit skills for security and prompt injection.

Acceptance: shared standard applies to all agent roles; role-to-capability map distinguishes available, missing and not verified; adversarial review is explicit; skill trust is content/version scoped, not blanket trust; unsafe authority overrides, credential exposure, remote execution, exfiltration and transitive dependency risks are reviewed. No claim of injection-proof safety. Tests cover relevant behavior; independent code/security review before final tests. No broker, database, protection, production or credential mutation. Do not install unreviewed third-party code. Preserve other agents' changes. Changes in isolated source worktree only; do not hand-edit generated installed copies.

Ownership: implementation agent owns shared guide, reviewer prompt, capability/security documentation and bounded tests. Security agent reads existing skills and reports findings without execution or modification. Orchestrator integrates and verifies. DONE: reviewed source changes with passing relevant checks and a precise installation/activation status.

## Follow-up: self-contained generated agents

Operator correction: linking a shared guide does not put the requirements into each agent file. Change canonical renderer to embed the complete shared contract in every generated specialist, including bundles, preserving role instructions/frontmatter and failing explicitly when source guide is missing. Keep shared source authoritative (no hand-maintained duplicates). Tests verify actual embedded content across all sources, changes propagate, no duplicate embedding. Include reviewable generated examples. Independent review precedes tests. Keep new revision staged for operator review; do not push/merge or overwrite installed files during this follow-up.
