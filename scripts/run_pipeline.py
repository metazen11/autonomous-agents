#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from autonomous_pipeline.adapters.github import GitHubAdapter
from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.config import load_runtime_config, merge_cli_overrides
from autonomous_pipeline.memory.agent_memory import AgentMemoryClient
from autonomous_pipeline.runner import PipelineRunner
from autonomous_pipeline.schemas import PromotionCandidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous pipeline runtime skeleton")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--todo-path", default=None, help="Path to todo.json")
    parser.add_argument("--memory-url", default=None, help="agent-memory base URL")
    parser.add_argument("--mode", choices=["dry_run", "full"], default="full")
    parser.add_argument(
        "--action",
        choices=[
            "init",
            "pick",
            "plan-demo",
            "remember-demo",
            "dev-demo",
            "code-review-demo",
            "verify-demo",
            "list-specialists",
            "show-specialist",
            "specialist-demo",
            "report-demo",
            "promote-demo",
            "review-demo",
            "improve-demo",
            "pr-demo",
            "full-demo",
        ],
        default="pick",
        help="Skeleton action to run",
    )
    parser.add_argument("--specialist", default="code-reviewer", help="Specialist name for show-specialist")
    parser.add_argument("--summary", default="Pipeline result placeholder", help="Summary for report-demo")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    config = merge_cli_overrides(
        load_runtime_config(repo_root),
        todo_path=args.todo_path,
        memory_url=args.memory_url,
    )
    adapter = build_adapter(repo_root, config)
    memory_client = AgentMemoryClient(base_url=config.memory_url)
    runner = PipelineRunner(
        repo_root=repo_root,
        adapter=adapter,
        config=config,
        memory_client=memory_client,
        mode=args.mode,
    )

    if args.action == "init":
        state = runner.initialize()
        print(json.dumps(state.to_dict(), indent=2))
        return 0

    runner.initialize()

    if args.action == "pick":
        task = runner.pick_task()
        print(json.dumps(task.to_dict() if task else {"task": None}, indent=2))
        return 0

    if args.action == "plan-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        updated = runner.report_planning(task, "Planning placeholder recorded by runtime skeleton")
        print(json.dumps(updated.to_dict(), indent=2))
        return 0

    if args.action == "remember-demo":
        lesson = runner.remember_lesson(
            title="Promote repeated verification commands",
            rule="When the same verification sequence succeeds repeatedly, capture it as a playbook or script.",
        )
        print(json.dumps(lesson or {"memory": "unavailable"}, indent=2))
        return 0

    if args.action == "dev-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_development(task), indent=2))
        return 0

    if args.action == "verify-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_verification(task), indent=2))
        return 0

    if args.action == "code-review-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_code_review(task), indent=2))
        return 0

    if args.action == "list-specialists":
        print(json.dumps(runner.list_specialist_contracts(), indent=2))
        return 0

    if args.action == "show-specialist":
        print(json.dumps(runner.get_specialist_contract(args.specialist), indent=2))
        return 0

    if args.action == "specialist-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_specialist(task, args.specialist), indent=2))
        return 0

    if args.action == "report-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        updated = runner.report_result(task, success=True, summary=args.summary)
        print(json.dumps(updated.to_dict(), indent=2))
        return 0

    if args.action == "promote-demo":
        result = runner.promote_candidate(
            PromotionCandidate(
                title="Promote repeated verification chain",
                description="Repeated build/lint/test sequence should become a reusable playbook or script.",
                source_evidence=["verify-demo"],
                expected_benefit="reduce repeated command entry",
                candidate_type="script",
            )
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.action == "review-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_review(task), indent=2))
        return 0

    if args.action == "improve-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        print(json.dumps(runner.run_improvement(task), indent=2))
        return 0

    if args.action == "pr-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        result = runner.prepare_pr(task)
        print(json.dumps(asdict(result), indent=2))
        return 0

    if args.action == "full-demo":
        task = runner.pick_task()
        if task is None:
            task = runner.get_selected_task()
        if task is None:
            print(json.dumps({"task": None}, indent=2))
            return 0
        planning = runner.report_planning(task, "Planning placeholder recorded by runtime skeleton")
        current_task = runner.adapter.get_task(planning.id)
        development = runner.run_development(current_task)
        code_review = runner.run_code_review(current_task)
        current_task = runner.adapter.get_task(planning.id)
        verification = runner.run_verification(current_task)
        current_task = runner.adapter.get_task(planning.id)
        review = runner.run_review(current_task)
        improvement = runner.run_improvement(current_task)
        current_task = runner.adapter.get_task(planning.id)
        success = (
            code_review["status"] == "success"
            and code_review["verdict"] == "approved"
            and all(item["status"] == "pass" for item in verification)
            and review["status"] == "success"
            and review["verdict"] == "approved"
        )
        reported = runner.report_result(current_task, success=success, summary=args.summary)
        print(
            json.dumps(
                {
                    "task": reported.to_dict(),
                    "development": development,
                    "code_review": code_review,
                    "verification": verification,
                    "review": review,
                    "improvement": improvement,
                },
                indent=2,
            )
        )
        return 0

    print(f"Unsupported action: {args.action}", file=sys.stderr)
    return 1


def build_adapter(repo_root: Path, config) -> object:
    if config.task_source == "todo_json":
        return TodoJsonAdapter(repo_root / config.todo_path)
    if config.task_source == "github":
        return GitHubAdapter(
            repo_root=repo_root,
            repo=config.github_repo,
            label=config.github_label,
            skip_labels=config.github_skip_labels,
            gh_command=config.github_command,
        )
    raise SystemExit(f"Unsupported task source: {config.task_source}")


if __name__ == "__main__":
    raise SystemExit(main())
