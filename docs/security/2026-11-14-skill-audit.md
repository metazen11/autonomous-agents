# Scoped skill security audit, 2026-11-14

Independent static review: skill_security agent, separate from implementation. No skill helpers, SQL, downloads or install hooks executed. 38 Markdown files inspected in the three installed bundles below; exact file digests in `2026-11-14-skills.sha256`. This host-specific record is not a portable blanket allowlist. Resolve the current directory, compare file inventory as well as hashes before use; added files or changed dependencies invalidate the review. `shasum -a 256 -c docs/security/2026-11-14-skills.sha256` checks recorded bytes, NOT added files or safety. No guarantee of injection immunity or correctness.

| Skill | Availability | Reviewed use and limits |
|---|---|---|
| `/Users/mz/.agents/skills/fullstack-dev/SKILL.md` | Installed, one prose file | Bounded backend design reference. No executable helpers, exfiltration, telemetry or operative malicious override found. Stylistic mandates remain subordinate to user and project architecture. |
| `/Users/mz/.agents/skills/frontend-design/SKILL.md` | Installed, one prose file | Bounded frontend design reference; same limitations. Not a QA substitute. |
| `/Users/mz/.agents/skills/supabase-postgres-best-practices/` | Installed, 36 Markdown files | Conditional database reference, not authorization to execute SQL. Caller-settable `app.current_user_id` RLS examples require a trusted context setter and a threat model that prevents arbitrary SQL; never adopt as identity proof without those controls. ALTER SYSTEM, reset-statistics and DROP examples require separate task authority. |

## Workflow findings and remediation

The installed autonomous wrapper matches source `pipeline/autonomous.md`. Its broad push-through rule and unresolved child workflows must not override authority or bypass failures. Source remediation makes that boundary explicit. `/autonomous-drain`, `/improve`, `/sprint-close` and project scripts are NOT approved transitively by this review.

`skills/capture/skill.md` and `agents/tasker.md` can create external tracker records. Before remediation they did not clearly distinguish operator requests from retrieved content or require sanitization before external filing. Source changes restrict origin, destination, scope and error reporting. Adapter response text remains untrusted and may echo sensitive data; do not print or transmit raw errors. External adapter/runtime behavior was only partially traced, not dynamically tested: these workflows are NOT blanket approved for external writes.

## Remaining gaps

No new third-party skill was installed. Other installed skills, plugin updates, runtime model competence, model availability and tool registration are not certified here. Skill security is enforced partly by host permissions and careful dispatch, not by Markdown alone. A skill review cannot grant production, broker, credential, merge or messaging authority.
