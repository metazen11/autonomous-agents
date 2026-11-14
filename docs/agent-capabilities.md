# Agent capabilities and activation status

The operational senior-specialist, independent-review, skill-trust and role routing
contract lives in [the shared guide](../agents/AGENT_AGNOSTIC_GUIDE.md). Host sync
embeds the complete canonical guide into every generated specialist, including
bundles and benched agents, while preserving the role body and frontmatter.
Source templates can retain shared-guide links; generated Markdown is self-contained.
The renderer requires an explicit repository root and fails if its canonical guide
is missing, empty or contains recursive generated markers. Re-rendering replaces
the generated contract block so updates propagate without duplicate embedding. Prompt existence does not establish runtime registration or model
capability.

## Scoped skill map — 2026-11-14

Host candidate paths are discovery locations, not portable installation promises:

| Role | Candidate source | Audit/use status |
|---|---|---|
| Backend implementer | `/Users/mz/.agents/skills/fullstack-dev/SKILL.md` | Scoped review recorded in the security report; verify hashes and relevant references before use |
| UI implementer | `/Users/mz/.agents/skills/frontend-design/SKILL.md` | Scoped review recorded in the security report; does not itself supply browser QA |
| Database specialist | `/Users/mz/.agents/skills/supabase-postgres-best-practices/SKILL.md` | Conditional: client-set user context is not identity proof; destructive SQL examples are not authorization |
| Supabase operations | `/Users/mz/.agents/skills/supabase/SKILL.md` | Unreviewed by this audit; not approved for activation by this change |
| Task capture | `skills/capture/skill.md`, `agents/tasker.md` | Source security fixes independently reviewed; external adapter chain remains only partially audited |
| Pipeline orchestration | `pipeline/autonomous.md` | Source authority/dependency fixes independently reviewed; child-skill availability and security remain per-host checks |
| Reviewer / auditor / QA | `agents/code-reviewer.md`, `agents/auditor.md`, `agents/qa-tester.md` | Prompt contracts exist; primary and backup model executions must be verified separately; no extra third-party skill required |
| Skill authoring | host-provided `skill-creator` | Consult when editing skills; availability is host-specific and does not authorize executing new helpers |

See [the security audit](security/2026-11-14-skill-audit.md) for the exact reviewed
files, findings, scope and limitations. Its hash inventory detects content drift;
it is not a signature, a runtime enforcement mechanism or an injection-proof claim.
No blanket approval extends to an entire skill directory, future version, remote
reference, install hook or newly discovered dependency.

This change does not select models, change credentials, install downloaded code,
register runtime roles or alter merge protection. The orchestrator must report
actual activation separately from source readiness. Use the existing host renderer
for installations; do not edit installed prompts by hand. Review the sync target
and deletions before any broad sync, which may affect unrelated installed agents.

Trading-vendored guide copies and pre-existing host TOML agent configurations are
separate artifacts: this source change does not automatically refresh them. Check
their referenced guide and actual dispatch route before claiming adoption.

## Reviewable generated examples

`review-artifacts/aa_code_reviewer.md` and `review-artifacts/aa_pm.md` contain the
fully expanded Markdown output for a core reviewer and a bundled project manager.
They are review artifacts, not installed or registered agents. The canonical guide
remains the one editable source; do not maintain copies by hand. The renderer's
`repo_root` argument must identify the prompt-pack source checkout, never a bundle
or an installed agent directory. It uses `agents/AGENT_AGNOSTIC_GUIDE.md` under that
root, not a guide found beside a bundled prompt.

This generator expands Markdown only. It does not generate or rewrite Codex TOML
role configurations; existing TOML roles and installed agents remain unchanged in
this follow-up. A source-template link is not evidence that a host loaded the full
contract. Inspect the expanded generated file and actual runtime dispatch route.
