# Issue acceptance criteria and audit phases

Keep acceptance criteria as numbered, testable checkboxes. Add this phase map
after the criteria and before implementation notes. The issue originator assigns
every criterion exactly once. Readiness and final evidence must be posted by the
authenticated originator or a repository admin/maintainer whose GitHub permission
is verified; the implementer does not change the criteria or phase map, and
unauthorized evidence actors are rejected by the validator.

```markdown
## Acceptance criteria
- [ ] <criterion text>
- [ ] <criterion text>

## Criterion phase map (owner-maintained)
<!-- reconcile-phase-map:v1
{"1":"PRE_LAND","2":"POST_LAND"}
-->
```

Use `PRE_LAND` for work that must be proven before integration. Use
`POST_LAND` only for outcomes that cannot exist until integration, such as a
criterion requiring the landing SHA to appear on the integration trunk. Keep
the original criterion text unchanged. The validator rejects missing,
duplicate, unknown, or invalid phase assignments.

The pre-integration auditor verifies every `PRE_LAND` criterion and returns
`READY_TO_RECONCILE` for legacy two-trunk integration or `READY_TO_MERGE` for
the PR path. These are readiness verdicts, never final PASS. After integration,
a fresh auditor verifies every criterion against the landed SHA; only final
`PASS` permits issue closure.

## Structured evidence comments

The authenticated issue originator or verified repository admin/maintainer
stores the quoted independent reports inside the evidence record so the
validator can require both reports and bind them to the same candidate SHA.
For PR readiness, include the exact issue URL in the PR body without a closing
keyword; the issue must remain open for the post-land audit. Legacy readiness
belongs on the issue; PR readiness belongs on the PR. Final PASS belongs on the
issue for either flow.

```json
{
  "issue": 29,
  "stage": "READY_TO_RECONCILE",
  "candidate_sha": "<full-sha>",
  "base_ref": "<integration-ref>",
  "base_sha": "<full-sha>",
  "review": {
    "status": "APPROVE",
    "sha": "<full-sha>",
    "report": "<quoted independent review report>"
  },
  "audit": {
    "status": "READY_TO_RECONCILE",
    "sha": "<full-sha>",
    "report": "<quoted independent readiness report>"
  },
  "criteria": {"1": "PASS", "2": "PASS", "3": "PENDING"}
}
```

Wrap that object in an HTML comment using the
`<!-- reconcile-evidence:v1 ... -->` marker. The PR flow uses
`READY_TO_MERGE` and the PR head/base refs. After integration, the issue's
`PASS` record must include `landed_sha`, `integration_ref`, a quoted
`audit_report`, and `PASS` for every mapped criterion.
