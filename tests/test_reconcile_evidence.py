from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_reconcile_evidence import (
    EvidenceError,
    _validate_issue_author,
    configured_integration_ref,
    configured_legacy_integration_ref,
    parse_phase_map,
    require_integration_ref,
    select_integration_ref,
    validate_integration_ref,
    validate_pr_target_marker,
    validate_pr_readiness,
    validate_final_audit,
    validate_readiness,
)


ISSUE_BODY = """## Acceptance criteria
- [ ] Policy is rendered.
- [ ] Reconciliation uses a safe checkout.
- [ ] The exact landing is verified.

## Scope
Implementation details.

<!-- reconcile-phase-map:v1
{"1":"PRE_LAND","2":"PRE_LAND","3":"POST_LAND"}
-->
"""

SHA_CANDIDATE = "a" * 40
SHA_BASE = "b" * 40
SHA_LANDED = "c" * 40


def evidence_comment(record: dict, *, author: str = "operator", created_at: str = "2026-11-24T12:00:00Z") -> dict:
    return {
        "author": {"login": author},
        "createdAt": created_at,
        "body": "<!-- reconcile-evidence:v1\n" + json.dumps(record) + "\n-->",
    }


def readiness_record(**overrides: object) -> dict:
    record = {
        "issue": 29,
        "stage": "READY_TO_RECONCILE",
        "candidate_sha": SHA_CANDIDATE,
        "base_ref": "origin/dev",
        "base_sha": SHA_BASE,
        "review": {
            "status": "APPROVE",
            "sha": SHA_CANDIDATE,
            "report": "Quoted independent review: APPROVE exact candidate SHA.",
        },
        "audit": {
            "status": "READY_TO_RECONCILE",
            "sha": SHA_CANDIDATE,
            "report": "Quoted independent audit: all PRE_LAND criteria PASS.",
        },
        "criteria": {"1": "PASS", "2": "PASS", "3": "PENDING"},
    }
    record.update(overrides)
    return record


class ReconcileEvidenceTest(unittest.TestCase):
    def test_issue_originator_or_verified_maintainer_can_post_evidence(self) -> None:
        _validate_issue_author({"author": {"login": "operator"}}, "operator")
        with patch("scripts.validate_reconcile_evidence._run", return_value="maintain") as run:
            _validate_issue_author({"author": {"login": "operator"}}, "maintainer", "owner/repo")
        run.assert_called_once_with(
            ["gh", "api", "repos/owner/repo/collaborators/maintainer/permission", "--jq", ".permission"]
        )
        with patch("scripts.validate_reconcile_evidence._run", return_value="write"):
            with self.assertRaisesRegex(EvidenceError, "verified repository admin/maintainer"):
                _validate_issue_author({"author": {"login": "owner"}}, "other-user", "owner/repo")

    def test_pr_readiness_rejects_matching_evidence_linked_to_another_issue(self) -> None:
        record = readiness_record(stage="READY_TO_MERGE", base_ref="main")
        record["audit"] = {
            "status": "READY_TO_MERGE",
            "sha": SHA_CANDIDATE,
            "report": "Quoted independent audit: all PRE_LAND criteria PASS.",
        }
        pull = {
            "body": "https://github.com/metazen11/autonomous-agents/issues/28",
            "closingIssuesReferences": [],
            "comments": [evidence_comment(record)],
        }
        with self.assertRaisesRegex(EvidenceError, "missing the requested issue link"):
            validate_pr_readiness(
                29,
                ISSUE_BODY,
                pull,
                "metazen11/autonomous-agents",
                "operator",
                SHA_CANDIDATE,
                "main",
                SHA_BASE,
            )

    def test_pr_readiness_accepts_nonclosing_exact_issue_link(self) -> None:
        record = readiness_record(stage="READY_TO_MERGE", base_ref="main")
        record["audit"] = {
            "status": "READY_TO_MERGE",
            "sha": SHA_CANDIDATE,
            "report": "Quoted independent audit: all PRE_LAND criteria PASS.",
        }
        pull = {
            "body": "Tracks https://github.com/metazen11/autonomous-agents/issues/29",
            "closingIssuesReferences": [],
            "comments": [evidence_comment(record)],
        }
        result = validate_pr_readiness(
            29,
            ISSUE_BODY,
            pull,
            "metazen11/autonomous-agents",
            "operator",
            SHA_CANDIDATE,
            "main",
            SHA_BASE,
        )
        self.assertEqual(result["stage"], "READY_TO_MERGE")

    def test_pr_issue_link_does_not_match_a_longer_issue_number(self) -> None:
        pull = {
            "body": "Tracks https://github.com/metazen11/autonomous-agents/issues/290",
            "closingIssuesReferences": [],
            "comments": [],
        }
        with self.assertRaisesRegex(EvidenceError, "missing the requested issue link"):
            validate_pr_readiness(
                29,
                ISSUE_BODY,
                pull,
                "metazen11/autonomous-agents",
                "operator",
                SHA_CANDIDATE,
                "main",
                SHA_BASE,
            )

    def test_pr_issue_link_rejects_path_suffix(self) -> None:
        pull = {
            "body": "Tracks https://github.com/metazen11/autonomous-agents/issues/29/foo",
            "closingIssuesReferences": [],
            "comments": [],
        }
        with self.assertRaisesRegex(EvidenceError, "missing the requested issue link"):
            validate_pr_readiness(
                29,
                ISSUE_BODY,
                pull,
                "metazen11/autonomous-agents",
                "operator",
                SHA_CANDIDATE,
                "main",
                SHA_BASE,
            )

    def test_pr_readiness_rejects_closing_issue_link_before_final_audit(self) -> None:
        pull = {
            "body": "Tracks https://github.com/metazen11/autonomous-agents/issues/29",
            "closingIssuesReferences": [
                {"number": 29, "url": "https://github.com/metazen11/autonomous-agents/issues/29"}
            ],
            "comments": [],
        }
        with self.assertRaisesRegex(EvidenceError, "without closing it"):
            validate_pr_readiness(
                29,
                ISSUE_BODY,
                pull,
                "metazen11/autonomous-agents",
                "operator",
                SHA_CANDIDATE,
                "main",
                SHA_BASE,
            )

    def test_canonical_docs_match_originator_or_maintainer_evidence_policy(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = (root / "docs/contract-reference.md").read_text()
        reconciler = (root / "agents/reconciler.md").read_text()
        template = (root / "docs/issue-acceptance-template.md").read_text()
        self.assertIn("issue originator or a verified repository admin/maintainer", contract)
        self.assertIn("originator or a verified repository admin/maintainer", reconciler)
        self.assertIn("originator or a repository admin/maintainer", template)

    def test_integration_target_uses_positive_opt_in_then_legacy_dev(self) -> None:
        self.assertEqual(
            select_integration_ref("origin/main", '{"model":"single-trunk"}', {"origin/dev"}),
            "origin/main",
        )
        self.assertEqual(
            select_integration_ref("origin/main", None, {"origin/dev", "origin/develop"}),
            "origin/dev",
        )
        with self.assertRaisesRegex(EvidenceError, "no dev/develop"):
            select_integration_ref("origin/main", None, set())

    def test_legacy_readiness_rejects_single_trunk_but_final_target_resolves_trunk(self) -> None:
        refs = {"origin/main", "origin/dev"}
        with (
            patch("scripts.validate_reconcile_evidence._has_ref", side_effect=lambda _root, ref: ref in refs),
            patch(
                "scripts.validate_reconcile_evidence._tree_file",
                return_value='{"model":"single-trunk"}',
            ),
        ):
            with self.assertRaisesRegex(EvidenceError, "single-trunk"):
                configured_legacy_integration_ref(Path("."))
            self.assertEqual(configured_integration_ref(Path(".")), "origin/main")

    def test_caller_cannot_select_a_non_configured_integration_ref(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "configured target"):
            require_integration_ref("origin/dev", "origin/topic")

    def test_pr_target_must_be_marked_single_trunk_production_trunk(self) -> None:
        validate_pr_target_marker("main", "feature/task", '{"model":"single-trunk"}')
        with self.assertRaisesRegex(EvidenceError, "production trunk"):
            validate_pr_target_marker("dev", "feature/task", '{"model":"single-trunk"}')
        with self.assertRaisesRegex(EvidenceError, "feature branch"):
            validate_pr_target_marker("main", "dev", '{"model":"single-trunk"}')
        with self.assertRaisesRegex(EvidenceError, "positively declare single-trunk"):
            validate_pr_target_marker("main", "feature/task", None)

    def test_complete_phase_map_and_readiness_pass(self) -> None:
        phase_map = parse_phase_map(ISSUE_BODY)
        self.assertEqual(phase_map, {"1": "PRE_LAND", "2": "PRE_LAND", "3": "POST_LAND"})

        record = readiness_record()
        checked = validate_readiness(
            29,
            ISSUE_BODY,
            [evidence_comment(record)],
            "operator",
            "legacy",
            SHA_CANDIDATE,
            "origin/dev",
            SHA_BASE,
        )
        self.assertEqual(checked["stage"], "READY_TO_RECONCILE")

    def test_incomplete_phase_map_is_rejected(self) -> None:
        body = ISSUE_BODY.replace('{"1":"PRE_LAND","2":"PRE_LAND","3":"POST_LAND"}', '{"1":"PRE_LAND","2":"PRE_LAND"}')
        with self.assertRaisesRegex(EvidenceError, "phase-map IDs mismatch"):
            parse_phase_map(body)

    def test_duplicate_phase_map_id_is_rejected(self) -> None:
        body = ISSUE_BODY.replace(
            '{"1":"PRE_LAND","2":"PRE_LAND","3":"POST_LAND"}',
            '{"1":"PRE_LAND","1":"PRE_LAND","2":"PRE_LAND","3":"POST_LAND"}',
        )
        with self.assertRaisesRegex(EvidenceError, "duplicate JSON key"):
            parse_phase_map(body)

    def test_unknown_phase_map_id_is_rejected(self) -> None:
        body = ISSUE_BODY.replace(
            '{"1":"PRE_LAND","2":"PRE_LAND","3":"POST_LAND"}',
            '{"1":"PRE_LAND","2":"PRE_LAND","4":"POST_LAND"}',
        )
        with self.assertRaisesRegex(EvidenceError, "phase-map IDs mismatch"):
            parse_phase_map(body)

    def test_stale_candidate_sha_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "candidate SHA is stale"):
            validate_readiness(
                29,
                ISSUE_BODY,
                [evidence_comment(readiness_record())],
                "operator",
                "legacy",
                "d" * 40,
                "origin/dev",
                SHA_BASE,
            )

    def test_wrong_issue_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "issue number does not match"):
            validate_readiness(
                30,
                ISSUE_BODY,
                [evidence_comment(readiness_record())],
                "operator",
                "legacy",
                SHA_CANDIDATE,
                "origin/dev",
                SHA_BASE,
            )

    def test_wrong_authenticated_actor_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "author does not match authenticated actor"):
            validate_readiness(
                29,
                ISSUE_BODY,
                [evidence_comment(readiness_record(), author="another-user")],
                "operator",
                "legacy",
                SHA_CANDIDATE,
                "origin/dev",
                SHA_BASE,
            )

    def test_wrong_release_stage_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "stage must be READY_TO_MERGE"):
            validate_readiness(
                29,
                ISSUE_BODY,
                [evidence_comment(readiness_record())],
                "operator",
                "pr",
                SHA_CANDIDATE,
                "dev",
                SHA_BASE,
            )

    def test_postland_criterion_must_be_pending_before_reconcile(self) -> None:
        record = readiness_record(criteria={"1": "PASS", "2": "PASS", "3": "PASS"})
        with self.assertRaisesRegex(EvidenceError, "criterion 3 must be PENDING"):
            validate_readiness(
                29,
                ISSUE_BODY,
                [evidence_comment(record)],
                "operator",
                "legacy",
                SHA_CANDIDATE,
                "origin/dev",
                SHA_BASE,
            )

    def test_newest_evidence_comment_controls_actor_and_stage(self) -> None:
        older = evidence_comment(readiness_record(), created_at="2026-11-24T11:00:00Z")
        newer = evidence_comment(readiness_record(), author="different", created_at="2026-11-24T12:00:00Z")
        with self.assertRaisesRegex(EvidenceError, "author does not match authenticated actor"):
            validate_readiness(
                29,
                ISSUE_BODY,
                [newer, older],
                "operator",
                "legacy",
                SHA_CANDIDATE,
                "origin/dev",
                SHA_BASE,
            )

    def test_final_pass_requires_all_criteria_and_reachable_landed_sha(self) -> None:
        record = {
            "issue": 29,
            "stage": "PASS",
            "landed_sha": SHA_LANDED,
            "integration_ref": "origin/dev",
            "audit_report": "Quoted fresh final audit: every criterion PASS.",
            "criteria": {"1": "PASS", "2": "PASS", "3": "PASS"},
        }
        checked = validate_final_audit(
            29,
            ISSUE_BODY,
            [evidence_comment(record)],
            "operator",
            "origin/dev",
            SHA_BASE,
            lambda landed, ref: landed == SHA_LANDED and ref == "origin/dev",
        )
        self.assertEqual(checked["landed_sha"], SHA_LANDED)

        with self.assertRaisesRegex(EvidenceError, "not reachable"):
            validate_final_audit(
                29,
                ISSUE_BODY,
                [evidence_comment(record)],
                "operator",
                "origin/dev",
                SHA_BASE,
                lambda _landed, _ref: False,
            )

    def test_final_pass_rejects_pending_postland_criterion(self) -> None:
        record = {
            "issue": 29,
            "stage": "PASS",
            "landed_sha": SHA_LANDED,
            "integration_ref": "origin/dev",
            "audit_report": "Quoted fresh final audit: criteria still checked.",
            "criteria": {"1": "PASS", "2": "PASS", "3": "PENDING"},
        }
        with self.assertRaisesRegex(EvidenceError, "criterion 3 must be PASS"):
            validate_final_audit(
                29,
                ISSUE_BODY,
                [evidence_comment(record)],
                "operator",
                "origin/dev",
                SHA_BASE,
                lambda _landed, _ref: True,
            )


if __name__ == "__main__":
    unittest.main()
