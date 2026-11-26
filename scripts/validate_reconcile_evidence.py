#!/usr/bin/env python3
"""Fail-closed validation for staged issue audit evidence used by /reconcile."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


PHASE_MAP_MARKER = "<!-- reconcile-phase-map:v1"
EVIDENCE_MARKER = "<!-- reconcile-evidence:v1"
BLOCK_RE = re.compile(r"<!--\s*([\w-]+:v1)\s*(.*?)\s*-->", re.DOTALL)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PHASES = {"PRE_LAND", "POST_LAND"}
READINESS_STAGES = {"legacy": "READY_TO_RECONCILE", "pr": "READY_TO_MERGE"}
TRUNK_REFS = ("origin/main", "origin/master")
LEGACY_INTEGRATION_REFS = ("origin/dev", "origin/develop")


class EvidenceError(ValueError):
    """Evidence is missing, malformed, stale, or does not match this release."""


@dataclass(frozen=True)
class EvidenceComment:
    record: dict[str, Any]
    author: str
    created_at: datetime


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, EvidenceError) as exc:
        raise EvidenceError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def acceptance_criteria(body: str) -> list[str]:
    """Return sequential IDs for checked/unchecked bullets in the AC section."""
    headings = list(re.finditer(r"(?im)^#{1,6}\s+acceptance criteria\s*$", body))
    if len(headings) != 1:
        raise EvidenceError("issue must have exactly one Acceptance criteria section")
    start = headings[0].end()
    next_heading = re.search(r"(?m)^#{1,6}\s+", body[start:])
    section = body[start : start + next_heading.start()] if next_heading else body[start:]
    criteria = re.findall(r"(?m)^\s*[-*+]\s+\[[ xX]\]\s+\S.*$", section)
    if not criteria:
        raise EvidenceError("Acceptance criteria section has no checkbox criteria")
    return [str(index) for index in range(1, len(criteria) + 1)]


def _one_marker_block(text: str, marker: str, label: str) -> str:
    count = text.count(marker)
    if count != 1:
        raise EvidenceError(f"expected exactly one {label} block, found {count}")
    matches = [match for match in BLOCK_RE.finditer(text) if match.group(0).startswith(marker)]
    if len(matches) != 1:
        raise EvidenceError(f"malformed {label} block")
    return matches[0].group(2).strip()


def parse_phase_map(body: str) -> dict[str, str]:
    """Validate the complete owner-maintained phase map against issue criteria."""
    raw = _one_marker_block(body, PHASE_MAP_MARKER, "phase-map")
    phase_map = _decode_json_object(raw, "phase-map")
    criteria_ids = acceptance_criteria(body)
    if set(phase_map) != set(criteria_ids):
        missing = sorted(set(criteria_ids) - set(phase_map), key=int)
        unknown = sorted(set(phase_map) - set(criteria_ids))
        raise EvidenceError(f"phase-map IDs mismatch (missing={missing}, unknown={unknown})")
    for criterion_id, phase in phase_map.items():
        if phase not in PHASES:
            raise EvidenceError(f"criterion {criterion_id} has invalid phase {phase!r}")
    return phase_map


def _parse_timestamp(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EvidenceError("evidence comment has an invalid createdAt") from exc
    if parsed.tzinfo is None:
        raise EvidenceError("evidence comment createdAt must include a timezone")
    return parsed


def newest_evidence_comment(comments: list[dict[str, Any]]) -> EvidenceComment:
    """Parse the newest evidence-bearing comment; malformed evidence fails closed."""
    evidence: list[EvidenceComment] = []
    for comment in comments:
        text = comment.get("body")
        if not isinstance(text, str) or EVIDENCE_MARKER not in text:
            continue
        raw = _one_marker_block(text, EVIDENCE_MARKER, "evidence")
        record = _decode_json_object(raw, "evidence")
        author = comment.get("author")
        if isinstance(author, dict):
            author = author.get("login")
        if not isinstance(author, str) or not author:
            raise EvidenceError("evidence comment has no author")
        created_at = comment.get("createdAt") or comment.get("created_at")
        evidence.append(EvidenceComment(record, author, _parse_timestamp(created_at)))
    if not evidence:
        raise EvidenceError("no reconcile evidence comment found")
    evidence.sort(key=lambda item: item.created_at)
    return evidence[-1]


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise EvidenceError(f"{field} must be a full 40-character commit SHA")
    return value


def _require_report(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value.strip()) < 20:
        raise EvidenceError(f"{field} must include the quoted report")
    return value


def _validate_actor(evidence: EvidenceComment, current_actor: str) -> None:
    if not current_actor or evidence.author != current_actor:
        raise EvidenceError("newest evidence comment author does not match authenticated actor")


def _validate_issue_author(
    issue: dict[str, Any], current_actor: str, repo: str | None = None
) -> None:
    author = issue.get("author")
    if isinstance(author, dict):
        author = author.get("login")
    if not isinstance(author, str) or not author:
        raise EvidenceError("issue response is missing its originator")
    if current_actor == author:
        return
    if not repo:
        raise EvidenceError("cannot verify delegated orchestrator without repository identity")
    permission = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/collaborators/{current_actor}/permission",
            "--jq",
            ".permission",
        ]
    )
    if permission not in {"admin", "maintain"}:
        raise EvidenceError(
            "authenticated orchestrator must be the issue originator or a verified repository admin/maintainer"
        )


def _validate_criterion_statuses(
    record: dict[str, Any], phase_map: dict[str, str], *, final: bool
) -> None:
    statuses = record.get("criteria")
    if not isinstance(statuses, dict) or set(statuses) != set(phase_map):
        raise EvidenceError("evidence criteria must cover every mapped criterion exactly once")
    for criterion_id, phase in phase_map.items():
        expected = "PASS" if final or phase == "PRE_LAND" else "PENDING"
        if statuses.get(criterion_id) != expected:
            raise EvidenceError(
                f"criterion {criterion_id} must be {expected} at this audit stage"
            )


def validate_readiness(
    issue_number: int,
    issue_body: str,
    comments: list[dict[str, Any]],
    current_actor: str,
    release_mode: str,
    candidate_sha: str,
    base_ref: str,
    base_sha: str,
) -> dict[str, Any]:
    """Validate current candidate/base review and readiness evidence."""
    if release_mode not in READINESS_STAGES:
        raise EvidenceError("release mode must be 'legacy' or 'pr'")
    candidate_sha = _require_sha(candidate_sha, "candidate SHA")
    base_sha = _require_sha(base_sha, "base SHA")
    if not base_ref:
        raise EvidenceError("base ref is required")
    phase_map = parse_phase_map(issue_body)
    evidence = newest_evidence_comment(comments)
    _validate_actor(evidence, current_actor)
    record = evidence.record
    expected_stage = READINESS_STAGES[release_mode]
    if record.get("issue") != issue_number:
        raise EvidenceError("evidence issue number does not match requested issue")
    if record.get("stage") != expected_stage:
        raise EvidenceError(f"evidence stage must be {expected_stage}")
    if _require_sha(record.get("candidate_sha"), "evidence candidate SHA") != candidate_sha:
        raise EvidenceError("candidate SHA is stale or mismatched")
    if record.get("base_ref") != base_ref:
        raise EvidenceError("base ref is stale or mismatched")
    if _require_sha(record.get("base_sha"), "evidence base SHA") != base_sha:
        raise EvidenceError("base SHA is stale or mismatched")

    review = record.get("review")
    audit = record.get("audit")
    if not isinstance(review, dict) or review.get("status") != "APPROVE":
        raise EvidenceError("readiness requires an APPROVE review")
    if _require_sha(review.get("sha"), "review SHA") != candidate_sha:
        raise EvidenceError("review SHA does not match candidate SHA")
    _require_report(review.get("report"), "review report")
    if not isinstance(audit, dict) or audit.get("status") != expected_stage:
        raise EvidenceError(f"audit status must be {expected_stage}")
    if _require_sha(audit.get("sha"), "audit SHA") != candidate_sha:
        raise EvidenceError("audit SHA does not match candidate SHA")
    _require_report(audit.get("report"), "audit report")
    _validate_criterion_statuses(record, phase_map, final=False)
    return record


def validate_final_audit(
    issue_number: int,
    issue_body: str,
    comments: list[dict[str, Any]],
    current_actor: str,
    integration_ref: str,
    ref_sha: str,
    is_ancestor: Callable[[str, str], bool],
) -> dict[str, Any]:
    """Validate final full-issue PASS against a commit reachable from integration."""
    if not integration_ref:
        raise EvidenceError("integration ref is required")
    ref_sha = _require_sha(ref_sha, "current integration SHA")
    phase_map = parse_phase_map(issue_body)
    evidence = newest_evidence_comment(comments)
    _validate_actor(evidence, current_actor)
    record = evidence.record
    if record.get("issue") != issue_number:
        raise EvidenceError("evidence issue number does not match requested issue")
    if record.get("stage") != "PASS":
        raise EvidenceError("final evidence stage must be PASS")
    _require_report(record.get("audit_report"), "final audit report")
    if record.get("integration_ref") != integration_ref:
        raise EvidenceError("integration ref is stale or mismatched")
    landed_sha = _require_sha(record.get("landed_sha"), "landed SHA")
    if not is_ancestor(landed_sha, integration_ref):
        raise EvidenceError("landed SHA is not reachable from the integration ref")
    _validate_criterion_statuses(record, phase_map, final=True)
    return record


def _run(command: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise EvidenceError(f"cannot run {command[0]}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise EvidenceError(f"{command[0]} failed: {detail}")
    return result.stdout.strip()


def _issue_snapshot(repo: str, issue_number: int) -> dict[str, Any]:
    raw = _run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "number,body,comments,state,author",
        ]
    )
    try:
        issue = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvidenceError("gh issue view returned invalid JSON") from exc
    if not isinstance(issue, dict) or issue.get("number") != issue_number:
        raise EvidenceError("GitHub returned a different issue")
    if not isinstance(issue.get("body"), str) or not isinstance(issue.get("comments"), list):
        raise EvidenceError("GitHub issue response is missing body or comments")
    if not isinstance(issue.get("author"), dict) or not issue["author"].get("login"):
        raise EvidenceError("GitHub issue response is missing the issue author")
    return issue


def _current_actor() -> str:
    actor = _run(["gh", "api", "user", "--jq", ".login"])
    if not actor:
        raise EvidenceError("cannot determine authenticated GitHub actor")
    return actor


def _git_sha(repo_root: Path, ref: str) -> str:
    if not ref or ref.startswith("-"):
        raise EvidenceError("invalid Git ref")
    sha = _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo_root)
    return _require_sha(sha, f"resolved ref {ref}")


def _tree_file(repo_root: Path, ref: str, path: str) -> str | None:
    names = _run(["git", "ls-tree", "--name-only", ref, "--", path], cwd=repo_root)
    if not names:
        return None
    return _run(["git", "show", f"{ref}:{path}"], cwd=repo_root)


def _is_single_trunk_content(content: str | None) -> bool:
    if content is None:
        return False
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return False
    return value == {"model": "single-trunk"}


def configured_integration_ref(repo_root: Path) -> str:
    """Resolve the only valid integration ref from the repo's checked-in model."""
    trunk_ref = next((ref for ref in TRUNK_REFS if _has_ref(repo_root, ref)), None)
    if trunk_ref is None:
        raise EvidenceError("cannot resolve main/master integration trunk")
    marker = _tree_file(repo_root, trunk_ref, ".reconcile-gate.json")
    available_refs = {ref for ref in LEGACY_INTEGRATION_REFS if _has_ref(repo_root, ref)}
    return select_integration_ref(trunk_ref, marker, available_refs)


def configured_legacy_integration_ref(repo_root: Path) -> str:
    """Resolve dev/develop only, refusing legacy readiness in single-trunk repos."""
    trunk_ref = next((ref for ref in TRUNK_REFS if _has_ref(repo_root, ref)), None)
    if trunk_ref is None:
        raise EvidenceError("cannot resolve main/master integration trunk")
    marker = _tree_file(repo_root, trunk_ref, ".reconcile-gate.json")
    if _is_single_trunk_content(marker):
        raise EvidenceError("legacy readiness is invalid for a single-trunk repository")
    available_refs = {ref for ref in LEGACY_INTEGRATION_REFS if _has_ref(repo_root, ref)}
    return select_integration_ref(trunk_ref, marker, available_refs)


def select_integration_ref(
    trunk_ref: str,
    marker_content: str | None,
    available_legacy_refs: set[str],
) -> str:
    """Apply positive single-trunk opt-in, otherwise select dev then develop."""
    if _is_single_trunk_content(marker_content):
        return trunk_ref
    integration_ref = next((ref for ref in LEGACY_INTEGRATION_REFS if ref in available_legacy_refs), None)
    if integration_ref is None:
        raise EvidenceError("legacy repository has no dev/develop integration ref")
    return integration_ref


def _has_ref(repo_root: Path, ref: str) -> bool:
    if not ref.startswith("origin/") or "/" in ref.removeprefix("origin/"):
        raise EvidenceError(f"unsupported integration ref name: {ref}")
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or f"exit {result.returncode}"
    raise EvidenceError(f"cannot inspect integration ref {ref}: {detail}")


def validate_integration_ref(repo_root: Path, supplied_ref: str) -> str:
    expected_ref = configured_integration_ref(repo_root)
    return require_integration_ref(expected_ref, supplied_ref)


def validate_legacy_integration_ref(repo_root: Path, supplied_ref: str) -> str:
    expected_ref = configured_legacy_integration_ref(repo_root)
    return require_integration_ref(expected_ref, supplied_ref)


def require_integration_ref(expected_ref: str, supplied_ref: str) -> str:
    if supplied_ref != expected_ref:
        raise EvidenceError(
            f"integration ref must be configured target {expected_ref}, not {supplied_ref}"
        )
    return supplied_ref


def _single_trunk_marker_content(repo: str, base_sha: str) -> str | None:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/contents/.reconcile-gate.json?ref={base_sha}",
            "--jq",
            ".content",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return None
    try:
        return base64.b64decode(result.stdout.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def validate_pr_target_marker(base_ref: str, head_ref: str, marker_content: str | None) -> None:
    if base_ref not in {"main", "master"}:
        raise EvidenceError("PR readiness is only valid for the production trunk base")
    if head_ref in {"main", "master", "dev", "develop"}:
        raise EvidenceError("PR readiness requires a feature branch, not an integration/trunk branch")
    if not _is_single_trunk_content(marker_content):
        raise EvidenceError("PR target must positively declare single-trunk at its base SHA")


def validate_pr_target(base_ref: str, head_ref: str, base_sha: str, repo: str) -> None:
    validate_pr_target_marker(
        base_ref, head_ref, _single_trunk_marker_content(repo, base_sha)
    )


def _require_open_issue(issue: dict[str, Any]) -> None:
    if str(issue.get("state", "")).upper() != "OPEN":
        raise EvidenceError("issue must remain open until final audit evidence is verified")


def _fetch_pr(repo: str, pr_number: int) -> dict[str, Any]:
    raw = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "number,state,headRefName,headRefOid,baseRefName,baseRefOid,body,comments,closingIssuesReferences",
        ]
    )
    try:
        pull = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvidenceError("gh pr view returned invalid JSON") from exc
    if not isinstance(pull, dict) or pull.get("number") != pr_number:
        raise EvidenceError("GitHub returned a different pull request")
    if str(pull.get("state", "")).upper() != "OPEN":
        raise EvidenceError("pull request must remain open until integration")
    return pull


def _require_pr_linked_issue(pull: dict[str, Any], repo: str, issue_number: int) -> None:
    """Require a non-closing PR-body link to the requested issue."""
    body = pull.get("body")
    if not isinstance(body, str):
        raise EvidenceError("GitHub pull request response is missing its body")
    expected_url = f"https://github.com/{repo}/issues/{issue_number}"
    body_urls = re.findall(r"https://[^\s<>()]+", body)
    if expected_url not in {url.rstrip(".,;:!?") for url in body_urls}:
        raise EvidenceError("pull request body is missing the requested issue link")

    references = pull.get("closingIssuesReferences")
    if not isinstance(references, list):
        raise EvidenceError("GitHub pull request response is missing closing-issue references")
    expected_path = f"/{repo}/issues/{issue_number}"
    for reference in references:
        if not isinstance(reference, dict):
            continue
        url = reference.get("url")
        if (
            reference.get("number") == issue_number
            and isinstance(url, str)
            and urlparse(url).path.rstrip("/") == expected_path
        ):
            raise EvidenceError("PR must reference the requested issue without closing it")


def validate_pr_readiness(
    issue_number: int,
    issue_body: str,
    pull: dict[str, Any],
    repo: str,
    current_actor: str,
    candidate_sha: str,
    base_ref: str,
    base_sha: str,
) -> dict[str, Any]:
    """Validate non-closing issue linkage and current PR readiness evidence."""
    _require_pr_linked_issue(pull, repo, issue_number)
    comments = pull.get("comments")
    if not isinstance(comments, list):
        raise EvidenceError("GitHub pull request response is missing comments")
    return validate_readiness(
        issue_number,
        issue_body,
        comments,
        current_actor,
        "pr",
        candidate_sha,
        base_ref,
        base_sha,
    )


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    legacy = subparsers.add_parser("legacy", help="verify legacy dev/develop readiness")
    legacy.add_argument("--repo", required=True, help="GitHub repository owner/name")
    legacy.add_argument("--issue", required=True, type=int)
    legacy.add_argument("--repo-root", type=Path, default=Path.cwd())
    legacy.add_argument("--integration-ref", required=True, help="for example origin/dev")

    pr = subparsers.add_parser("pr", help="verify PR readiness")
    pr.add_argument("--repo", required=True, help="GitHub repository owner/name")
    pr.add_argument("--issue", required=True, type=int)
    pr.add_argument("--pr", required=True, type=int)

    final = subparsers.add_parser("final", help="verify post-land full-issue PASS")
    final.add_argument("--repo", required=True, help="GitHub repository owner/name")
    final.add_argument("--issue", required=True, type=int)
    final.add_argument("--repo-root", type=Path, default=Path.cwd())
    final.add_argument("--integration-ref", required=True, help="for example origin/dev")
    return parser


def _is_ancestor(repo_root: Path, landed_sha: str, integration_ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", landed_sha, integration_ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or f"exit {result.returncode}"
    raise EvidenceError(f"cannot verify landed SHA reachability: {detail}")


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    try:
        issue = _issue_snapshot(args.repo, args.issue)
        _require_open_issue(issue)
        actor = _current_actor()
        _validate_issue_author(issue, actor, args.repo)

        if args.command == "legacy":
            root = args.repo_root.resolve()
            integration_ref = validate_legacy_integration_ref(root, args.integration_ref)
            candidate_sha = _git_sha(root, "HEAD")
            base_sha = _git_sha(root, integration_ref)
            validate_readiness(
                args.issue,
                issue["body"],
                issue["comments"],
                actor,
                "legacy",
                candidate_sha,
                integration_ref,
                base_sha,
            )
            print(f"READY_TO_RECONCILE VERIFIED: issue {args.issue} candidate {candidate_sha}")
            return 0

        if args.command == "pr":
            pull = _fetch_pr(args.repo, args.pr)
            candidate_sha = _require_sha(pull.get("headRefOid"), "PR head SHA")
            base_ref = pull.get("baseRefName")
            base_sha = _require_sha(pull.get("baseRefOid"), "PR base SHA")
            if not isinstance(base_ref, str) or not base_ref:
                raise EvidenceError("PR base ref is missing")
            head_ref = pull.get("headRefName")
            if not isinstance(head_ref, str) or not head_ref:
                raise EvidenceError("PR head ref is missing")
            validate_pr_target(base_ref, head_ref, base_sha, args.repo)
            validate_pr_readiness(
                args.issue,
                issue["body"],
                pull,
                args.repo,
                actor,
                candidate_sha,
                base_ref,
                base_sha,
            )
            print(
                f"READY_TO_MERGE VERIFIED: PR {args.pr} head {candidate_sha} "
                f"base {base_ref}@{base_sha}"
            )
            return 0

        root = args.repo_root.resolve()
        integration_ref = validate_integration_ref(root, args.integration_ref)
        current_sha = _git_sha(root, integration_ref)
        record = validate_final_audit(
            args.issue,
            issue["body"],
            issue["comments"],
            actor,
            integration_ref,
            current_sha,
            lambda landed, ref: _is_ancestor(
                root, landed, ref
            ),
        )
        landed_sha = _require_sha(record.get("landed_sha"), "landed SHA")
        print(f"FINAL PASS VERIFIED: issue {args.issue} landed {landed_sha}")
        return 0
    except EvidenceError as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
