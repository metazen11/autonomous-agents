from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from autonomous_pipeline.schemas import AgentResult, RunState, RuntimeConfig, Task
from autonomous_pipeline.schemas import SpecialistContract


SPECIALIST_CONTRACTS: dict[str, SpecialistContract] = {
    "code-reviewer": SpecialistContract(
        name="code-reviewer",
        prompt_file="agents/code-reviewer.md",
        mode="read_only",
        responsibilities=[
            "pre-test code quality review",
            "correctness review",
            "regression identification",
            "simplification and DRY enforcement",
            "naming and style convention enforcement",
            "documentation and dependency review",
        ],
        required_inputs=["base_ref", "head_ref", "task_title", "task_body", "changed_files"],
        optional_inputs=["acceptance_criteria", "repo_rules", "dependency_manifests"],
        output_keys=[
            "status",
            "summary",
            "verdict",
            "findings",
            "tests_missing",
            "dry_risks",
            "simplification_opportunities",
            "naming_style_concerns",
            "documentation_gaps",
            "dependency_concerns",
        ],
        escalation_conditions=["missing diff context", "unsafe repository state"],
    ),
    "qa-tester": SpecialistContract(
        name="qa-tester",
        prompt_file="agents/qa-tester.md",
        mode="bounded_write",
        responsibilities=["verification selection", "behavioral validation", "bug reproduction"],
        required_inputs=["task_title", "changed_files", "artifacts_dir"],
        optional_inputs=["acceptance_criteria", "build_command", "lint_command", "test_command", "ui_command"],
        allowed_write_scope_required=True,
        output_keys=["status", "summary", "verdict", "checks_run", "bugs_found", "artifacts"],
        escalation_conditions=["required environment missing", "test harness unavailable"],
    ),
    "security-auditor": SpecialistContract(
        name="security-auditor",
        prompt_file="agents/security-auditor.md",
        mode="read_only",
        responsibilities=["security review", "exploitability assessment"],
        required_inputs=["task_title", "task_body", "changed_files"],
        optional_inputs=["repo_rules"],
        output_keys=["status", "summary", "findings", "evidence"],
        escalation_conditions=["missing security-sensitive diff context"],
    ),
    "security-fixer": SpecialistContract(
        name="security-fixer",
        prompt_file="agents/security-fixer.md",
        mode="bounded_write",
        responsibilities=["bounded security remediation", "rollback-ready fixes"],
        required_inputs=["findings", "allowed_write_scope", "verification_commands"],
        optional_inputs=["acceptance_criteria", "artifacts_dir"],
        allowed_write_scope_required=True,
        output_keys=["status", "summary", "changes", "tests_run", "rollback", "residual_risks"],
        escalation_conditions=["required file outside write scope"],
    ),
    "dep-auditor": SpecialistContract(
        name="dep-auditor",
        prompt_file="agents/dep-auditor.md",
        mode="read_only",
        responsibilities=["dependency vulnerability assessment", "upgrade risk review"],
        required_inputs=["changed_files"],
        optional_inputs=["dependency_manifests"],
        output_keys=["status", "summary", "findings", "evidence"],
        escalation_conditions=["dependency metadata unavailable"],
    ),
    "db-analyst": SpecialistContract(
        name="db-analyst",
        prompt_file="agents/db-analyst.md",
        mode="read_only",
        responsibilities=["query analysis", "migration risk review", "database health assessment"],
        required_inputs=["changed_files"],
        optional_inputs=["database_type", "connection_method"],
        output_keys=["status", "summary", "findings", "sql_suggestions"],
        escalation_conditions=["safe read-only DB access unavailable"],
    ),
    "perf-profiler": SpecialistContract(
        name="perf-profiler",
        prompt_file="agents/perf-profiler.md",
        mode="read_only",
        responsibilities=["performance measurement", "baseline comparison"],
        required_inputs=["changed_files", "artifacts_dir"],
        optional_inputs=["target_urls", "baseline_metrics"],
        output_keys=["status", "summary", "metrics", "bottlenecks"],
        escalation_conditions=["target environment unavailable"],
    ),
    "infra-checker": SpecialistContract(
        name="infra-checker",
        prompt_file="agents/infra-checker.md",
        mode="read_only",
        responsibilities=["read-only environment validation", "service status checks"],
        required_inputs=["service_inventory"],
        optional_inputs=["domains", "containers", "cloud_resources"],
        output_keys=["status", "summary", "service_status", "warnings", "recommendations"],
        escalation_conditions=["infrastructure identifiers unavailable"],
    ),
    "soc2-auditor": SpecialistContract(
        name="soc2-auditor",
        prompt_file="agents/soc2-auditor.md",
        mode="read_only",
        responsibilities=["SOC 2 control gap review"],
        required_inputs=["audit_scope"],
        optional_inputs=["repo_rules", "infrastructure_metadata"],
        output_keys=["status", "summary", "findings", "follow_up"],
        escalation_conditions=["audit scope undefined"],
    ),
    "hipaa-auditor": SpecialistContract(
        name="hipaa-auditor",
        prompt_file="agents/hipaa-auditor.md",
        mode="read_only",
        responsibilities=["HIPAA technical safeguard review"],
        required_inputs=["audit_scope"],
        optional_inputs=["phi_boundaries", "auth_details"],
        output_keys=["status", "summary", "findings", "follow_up"],
        escalation_conditions=["PHI handling scope undefined"],
    ),
    "compliance-fixer": SpecialistContract(
        name="compliance-fixer",
        prompt_file="agents/compliance-fixer.md",
        mode="bounded_write",
        responsibilities=["bounded compliance remediation", "audit-ready evidence"],
        required_inputs=["findings", "allowed_write_scope", "verification_commands"],
        optional_inputs=["acceptance_criteria", "artifacts_dir"],
        allowed_write_scope_required=True,
        output_keys=["status", "summary", "changes", "tests_run", "rollback", "residual_risks"],
        escalation_conditions=["required file outside write scope"],
    ),
    "skill-promoter": SpecialistContract(
        name="skill-promoter",
        prompt_file="agents/skill-promoter.md",
        mode="read_only",
        responsibilities=["workflow mining", "promotion recommendations"],
        required_inputs=["artifacts_dir"],
        optional_inputs=["command_transcripts", "benchmark_data", "memory_entries"],
        output_keys=["status", "summary", "promotions", "retirements", "benchmarks_needed"],
        escalation_conditions=["insufficient artifact history"],
    ),
}


def get_specialist_contract(name: str) -> SpecialistContract:
    return SPECIALIST_CONTRACTS[name]


def list_specialist_contracts() -> list[SpecialistContract]:
    return [SPECIALIST_CONTRACTS[name] for name in sorted(SPECIALIST_CONTRACTS)]


def execute_specialist(
    name: str,
    *,
    repo_root: str | Path,
    artifacts_root: str | Path,
    task: Task,
    run_state: RunState,
    config: RuntimeConfig,
    stage: str | None = None,
) -> AgentResult:
    repo_root_path = Path(repo_root)
    artifacts_root_path = Path(artifacts_root)
    contract = get_specialist_contract(name)

    if name == "code-reviewer":
        return _execute_code_reviewer(contract, repo_root_path, artifacts_root_path, task, run_state, stage=stage or "REVIEW")
    if name == "qa-tester":
        return _execute_qa_tester(contract, artifacts_root_path, task)
    if name == "security-auditor":
        return _execute_security_auditor(contract, artifacts_root_path, task)
    if name == "dep-auditor":
        return _execute_dep_auditor(contract, artifacts_root_path, task)
    if name == "db-analyst":
        return _execute_db_analyst(contract, artifacts_root_path, task)
    if name == "perf-profiler":
        return _execute_perf_profiler(contract, artifacts_root_path, task)
    if name == "infra-checker":
        return _execute_infra_checker(contract, artifacts_root_path, task)
    if name == "soc2-auditor":
        return _execute_scope_auditor(contract, artifacts_root_path, task, scope_key="audit_scope")
    if name == "hipaa-auditor":
        return _execute_scope_auditor(contract, artifacts_root_path, task, scope_key="audit_scope")
    if name == "security-fixer":
        return _execute_bounded_fixer(contract, artifacts_root_path, task, domain="security")
    if name == "compliance-fixer":
        return _execute_bounded_fixer(contract, artifacts_root_path, task, domain="compliance")
    if name == "skill-promoter":
        return _execute_skill_promoter(contract, artifacts_root_path, task, config)

    artifact_path = _write_artifact(
        artifacts_root_path,
        name,
        {
            "status": "needs_human",
            "summary": f"Automated execution is not implemented for {name}",
            "contract": asdict(contract),
        },
    )
    return AgentResult(
        agent_name=name,
        status="needs_human",
        summary=f"Automated execution is not implemented for {name}",
        artifacts=[artifact_path],
    )


def _execute_code_reviewer(
    contract: SpecialistContract,
    repo_root: Path,
    artifacts_root: Path,
    task: Task,
    run_state: RunState,
    *,
    stage: str,
) -> AgentResult:
    verification_results = list(task.metadata.get("verification_results", []))
    changed_files = task.metadata.get("changed_files") or _git_changed_files(repo_root)
    findings: list[dict] = []
    dry_risks: list[str] = []
    simplification_opportunities: list[str] = []
    naming_style_concerns: list[str] = []
    documentation_gaps: list[str] = []
    dependency_concerns: list[str] = []

    if not changed_files:
        findings.append(
            {
                "severity": "medium",
                "title": "Limited diff context",
                "detail": "No changed files were detected from task metadata or git state.",
            }
        )

    if stage != "CODE_REVIEW" and not verification_results:
        findings.append(
            {
                "severity": "high",
                "title": "Missing verification evidence",
                "detail": "No verification results were recorded before review.",
            }
        )

    if stage != "CODE_REVIEW":
        for item in verification_results:
            if item.get("status") != "pass":
                findings.append(
                    {
                        "severity": "high",
                        "title": f"{item.get('category', 'unknown')} verification failed",
                        "detail": item.get("detail") or f"Command failed: {item.get('command')}",
                    }
                )

    dependency_files = [
        path for path in changed_files if path.endswith(("package.json", "package-lock.json", "pyproject.toml", "requirements.txt", "poetry.lock", "Pipfile", "Pipfile.lock"))
    ]
    if any(path.endswith(("package.json", "pyproject.toml", "requirements.txt", "Pipfile")) for path in dependency_files) and not any(
        path.endswith(("package-lock.json", "poetry.lock", "Pipfile.lock")) for path in dependency_files
    ):
        dependency_concerns.append("Dependency manifest changed without a matching lockfile update.")

    code_files = [path for path in changed_files if path.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rb", ".java"))]
    docs_files = [path for path in changed_files if path.endswith((".md", ".rst"))]
    if len(code_files) >= 3 and not docs_files:
        documentation_gaps.append("Multiple code files changed without accompanying docs or maintainers notes.")

    parent_dirs = {str(Path(path).parent) for path in code_files}
    if len(code_files) >= 3 and len(parent_dirs) == 1:
        dry_risks.append("Several code files changed in the same area; check for duplication or copy-paste drift.")
        simplification_opportunities.append("Consider extracting shared logic or consolidating repeated changes in one abstraction.")
    if any(" " in Path(path).name for path in changed_files):
        naming_style_concerns.append("Changed file set includes names with spaces; verify file naming conventions are being enforced.")

    if dependency_concerns:
        findings.extend(
            {
                "severity": "medium",
                "title": "Dependency hygiene concern",
                "detail": detail,
            }
            for detail in dependency_concerns
        )
    if documentation_gaps:
        findings.extend(
            {
                "severity": "low",
                "title": "Documentation gap",
                "detail": detail,
            }
            for detail in documentation_gaps
        )
    if dry_risks:
        findings.extend(
            {
                "severity": "medium",
                "title": "DRY risk",
                "detail": detail,
            }
            for detail in dry_risks
        )
    if naming_style_concerns:
        findings.extend(
            {
                "severity": "medium",
                "title": "Naming or style convention concern",
                "detail": detail,
            }
            for detail in naming_style_concerns
        )

    verdict = "approved" if verification_results and not findings else "changes_requested"
    if stage == "CODE_REVIEW":
        verdict = "approved" if not findings else "changes_requested"
    summary = (
        "Code review approved with recorded verification evidence."
        if verdict == "approved"
        else f"Code review requires changes; findings={len(findings)}"
    )
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {
            "status": "success",
            "summary": summary,
            "verdict": verdict,
            "findings": findings,
            "dry_risks": dry_risks,
            "simplification_opportunities": simplification_opportunities,
            "naming_style_concerns": naming_style_concerns,
            "documentation_gaps": documentation_gaps,
            "dependency_concerns": dependency_concerns,
            "changed_files": changed_files,
            "verification_results": verification_results,
            "stage": stage,
            "session_id": run_state.session_id,
        },
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=findings,
        evidence=changed_files,
        artifacts=[artifact_path],
        memory_status="loaded" if run_state.memory_status == "ok" else "unavailable",
    )


def _execute_qa_tester(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    verification_results = list(task.metadata.get("verification_results", []))
    passed = [item for item in verification_results if item.get("status") == "pass"]
    failed = [item for item in verification_results if item.get("status") != "pass"]
    summary = f"QA reviewed {len(verification_results)} verification checks; pass={len(passed)} fail={len(failed)}"
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {
            "status": "success",
            "summary": summary,
            "checks_run": verification_results,
            "bugs_found": failed,
        },
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=failed,
        evidence=[item.get("artifact_path") for item in verification_results if item.get("artifact_path")],
        artifacts=[artifact_path],
    )


def _execute_skill_promoter(
    contract: SpecialistContract,
    artifacts_root: Path,
    task: Task,
    config: RuntimeConfig,
) -> AgentResult:
    verification_results = list(task.metadata.get("verification_results", []))
    development_result = dict(task.metadata.get("development_result", {}))
    promotions: list[dict] = []

    if development_result.get("status") == "pass" and config.development_command:
        promotions.append(
            {
                "title": f"Promote development command for {task.title}",
                "description": f"Capture the successful DEV command as a reusable script: {config.development_command}",
                "candidate_type": "script",
                "expected_benefit": "reduce repeated manual implementation commands",
                "source_evidence": [development_result.get("artifact_path", "")],
            }
        )

    successful_verifications = [item for item in verification_results if item.get("status") == "pass"]
    if len(successful_verifications) >= 2:
        promotions.append(
            {
                "title": f"Promote verification playbook for {task.title}",
                "description": "Bundle the successful verification chain into a documented playbook or scripted workflow.",
                "candidate_type": "playbook",
                "expected_benefit": "reduce repeated build/lint/test entry and improve consistency",
                "source_evidence": [
                    item.get("artifact_path", "")
                    for item in successful_verifications
                    if item.get("artifact_path")
                ],
            }
        )

    summary = (
        f"Generated {len(promotions)} promotion candidate(s) from recorded DEV/TEST evidence."
        if promotions
        else "No promotion candidates were generated from the available evidence."
    )
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {
            "status": "success",
            "summary": summary,
            "promotions": promotions,
            "benchmarks_needed": [] if promotions else ["Need more repeated successful runs before promotion"],
        },
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=promotions,
        evidence=[item for item in [development_result.get("artifact_path")] if item] + [
            item.get("artifact_path") for item in verification_results if item.get("artifact_path")
        ],
        artifacts=[artifact_path],
    )


def _execute_security_auditor(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    changed_files = list(task.metadata.get("changed_files", []))
    findings: list[dict] = []
    sensitive_patterns = ("auth", "secret", "token", ".env", "credential", "middleware")
    for changed_file in changed_files:
        lowered = changed_file.lower()
        if any(pattern in lowered for pattern in sensitive_patterns):
            findings.append(
                {
                    "severity": "medium",
                    "title": "Security-sensitive file changed",
                    "detail": f"Review required for {changed_file}",
                }
            )

    for item in task.metadata.get("verification_results", []):
        if item.get("category") == "security" and item.get("status") != "pass":
            findings.append(
                {
                    "severity": "high",
                    "title": "Security verification failed",
                    "detail": item.get("detail") or f"Security command failed: {item.get('command')}",
                }
            )

    summary = f"Security audit completed with {len(findings)} finding(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "findings": findings, "changed_files": changed_files},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=findings,
        evidence=changed_files,
        artifacts=[artifact_path],
    )


def _execute_dep_auditor(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    changed_files = list(task.metadata.get("changed_files", []))
    findings: list[dict] = []
    manifests = [item for item in changed_files if item.endswith(("package.json", "package-lock.json", "pyproject.toml", "requirements.txt", "poetry.lock", "Pipfile", "Pipfile.lock"))]
    if manifests:
        lockfiles = [item for item in manifests if item.endswith(("package-lock.json", "poetry.lock", "Pipfile.lock"))]
        if any(item.endswith(("package.json", "pyproject.toml", "requirements.txt", "Pipfile")) for item in manifests) and not lockfiles:
            findings.append(
                {
                    "severity": "medium",
                    "title": "Dependency manifest changed without lockfile",
                    "detail": "Dependency changes should usually update the corresponding lockfile.",
                }
            )
    summary = f"Dependency audit completed with {len(findings)} finding(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "findings": findings, "manifests": manifests},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=findings,
        evidence=manifests,
        artifacts=[artifact_path],
    )


def _execute_db_analyst(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    changed_files = list(task.metadata.get("changed_files", []))
    findings: list[dict] = []
    db_files = [item for item in changed_files if _looks_like_database_file(item)]
    has_data_verification = any(item.get("category") == "data" and item.get("status") == "pass" for item in task.metadata.get("verification_results", []))
    if db_files and not has_data_verification:
        findings.append(
            {
                "severity": "medium",
                "title": "Database change lacks data verification",
                "detail": "SQL or migration changes were detected without a passing data verification step.",
            }
        )
    summary = f"Database analysis completed with {len(findings)} finding(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "findings": findings, "database_files": db_files},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=findings,
        evidence=db_files,
        artifacts=[artifact_path],
    )


def _execute_perf_profiler(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    verification_results = list(task.metadata.get("verification_results", []))
    perf_results = [item for item in verification_results if item.get("category") == "performance"]
    findings: list[dict] = []
    if not perf_results:
        findings.append(
            {
                "severity": "low",
                "title": "No performance baseline recorded",
                "detail": "No performance verification artifact was available for comparison.",
            }
        )
    summary = f"Performance profiling completed with {len(findings)} finding(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "findings": findings, "metrics": perf_results},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        findings=findings,
        evidence=[item.get("artifact_path") for item in perf_results if item.get("artifact_path")],
        artifacts=[artifact_path],
    )


def _execute_infra_checker(contract: SpecialistContract, artifacts_root: Path, task: Task) -> AgentResult:
    inventory = task.metadata.get("service_inventory")
    if not inventory:
        summary = "Infrastructure identifiers unavailable; read-only infra validation requires service inventory."
        artifact_path = _write_artifact(
            artifacts_root,
            contract.name,
            {"status": "needs_human", "summary": summary, "service_status": [], "warnings": ["service_inventory missing"]},
        )
        return AgentResult(
            agent_name=contract.name,
            status="needs_human",
            summary=summary,
            findings=[{"severity": "medium", "title": "Missing service inventory", "detail": summary}],
            artifacts=[artifact_path],
        )

    summary = f"Infrastructure checker reviewed {len(inventory)} declared service(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "service_status": inventory, "warnings": []},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        evidence=[str(item) for item in inventory],
        artifacts=[artifact_path],
    )


def _execute_scope_auditor(
    contract: SpecialistContract,
    artifacts_root: Path,
    task: Task,
    *,
    scope_key: str,
) -> AgentResult:
    scope = task.metadata.get(scope_key)
    if not scope:
        summary = f"{contract.name} requires {scope_key} metadata."
        artifact_path = _write_artifact(
            artifacts_root,
            contract.name,
            {"status": "needs_human", "summary": summary, "findings": [{"title": "Missing audit scope", "detail": summary}]},
        )
        return AgentResult(
            agent_name=contract.name,
            status="needs_human",
            summary=summary,
            findings=[{"severity": "medium", "title": "Missing audit scope", "detail": summary}],
            artifacts=[artifact_path],
        )

    summary = f"{contract.name} reviewed provided audit scope."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {"status": "success", "summary": summary, "findings": [], "scope": scope},
    )
    return AgentResult(
        agent_name=contract.name,
        status="success",
        summary=summary,
        evidence=[str(scope)],
        artifacts=[artifact_path],
    )


def _execute_bounded_fixer(
    contract: SpecialistContract,
    artifacts_root: Path,
    task: Task,
    *,
    domain: str,
) -> AgentResult:
    findings = list(task.metadata.get("findings", []))
    allowed_write_scope = list(task.metadata.get("allowed_write_scope", []))
    if not findings or not allowed_write_scope:
        summary = f"{contract.name} requires findings and allowed_write_scope before remediation can start."
        artifact_path = _write_artifact(
            artifacts_root,
            contract.name,
            {"status": "needs_human", "summary": summary, "changes": [], "rollback": "not attempted"},
        )
        return AgentResult(
            agent_name=contract.name,
            status="needs_human",
            summary=summary,
            findings=[{"severity": "medium", "title": f"Missing {domain} remediation context", "detail": summary}],
            artifacts=[artifact_path],
        )

    summary = f"{contract.name} produced a bounded remediation plan for {len(findings)} finding(s)."
    artifact_path = _write_artifact(
        artifacts_root,
        contract.name,
        {
            "status": "needs_human",
            "summary": summary,
            "changes": [],
            "tests_run": [],
            "rollback": "manual review required",
            "residual_risks": ["Automated file editing is not implemented for this fixer yet."],
            "allowed_write_scope": allowed_write_scope,
            "findings": findings,
        },
    )
    return AgentResult(
        agent_name=contract.name,
        status="needs_human",
        summary=summary,
        findings=findings,
        evidence=allowed_write_scope,
        artifacts=[artifact_path],
    )


def _write_artifact(artifacts_root: Path, specialist_name: str, payload: dict) -> str:
    artifacts_root.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_root / f"{specialist_name}-result.json"
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n")
    return str(artifact_path)


def _git_changed_files(repo_root: Path) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    changed_files: list[str] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        changed_files.append(line[3:])
    return changed_files


def _looks_like_database_file(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(".sql") or "migration" in lowered or "schema" in lowered or "/db/" in lowered or "alembic" in lowered
