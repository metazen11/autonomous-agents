#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autonomous_pipeline.host_sync import (
    HOST_AGENTS_CONFIG,
    HOST_NAMES,
    anacron_line,
    check_target,
    cron_line,
    discover_targets,
    feature_report,
    install_git_hooks,
    install_from_git_command,
    launchd_plist,
    load_dotenv,
    format_agent_inventory_report,
    host_bench_sources,
    reconcile_agent_inventory,
    set_bench,
    sync_agents_dir,
    sync_target,
    update_checkout_from_git,
    windows_task_command,
    windows_task_xml,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync prompt pack into configured host directories")
    parser.add_argument(
        "action",
        choices=[
            "sync",
            "check",
            "print-cron",
            "print-anacron",
            "print-launchd",
            "print-windows-task",
            "print-windows-xml",
            "write-launchd",
            "write-windows-xml",
            "install-git-hooks",
            "print-host-features",
            "print-install-command",
            "update-from-git",
            "update-and-sync",
            "reconcile-agents",
            "sync-agents",
            "bench",
        ],
        nargs="?",
        default="check",
    )
    parser.add_argument("bench_args", nargs="*", metavar="list | play NAME | sit NAME", help="bench action: play = make active, sit = bench")
    parser.add_argument("--host", action="append", default=[], help="bench play/sit: host(s) to change (default: every host in host_agents.json)")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--env-file", default=".env", help="Path to .env file relative to repo root or absolute")
    parser.add_argument("--python-bin", default=None, help="Python executable to use in generated commands/hooks")
    parser.add_argument("--output", default=None, help="Output path for write-* actions")
    parser.add_argument("--repo-url", default="https://github.com/metazen11/autonomous-agents.git", help="Git repository URL for print-install-command")
    parser.add_argument("--branch", default="main", help="Git branch for print-install-command")
    parser.add_argument("--agent-dir", action="append", default=[], help="Additional agent directory to compare during reconcile-agents")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = repo_root / env_path

    env = load_dotenv(env_path)
    targets = discover_targets(repo_root, env)
    python_bin = args.python_bin or sys.executable or "python3"

    if args.action == "print-host-features":
        print(feature_report())
        return 0

    if args.action == "print-install-command":
        print(
            install_from_git_command(
                repo_url=args.repo_url,
                install_dir=repo_root,
                branch=args.branch,
                python_bin=python_bin,
            )
        )
        return 0

    if args.action == "update-from-git":
        update_checkout_from_git(repo_url=args.repo_url, install_dir=repo_root, branch=args.branch)
        return 0

    if args.action == "update-and-sync":
        update_checkout_from_git(repo_url=args.repo_url, install_dir=repo_root, branch=args.branch)
        env = load_dotenv(env_path)
        targets = discover_targets(repo_root, env)
        if not targets:
            print("No host targets configured in .env", file=sys.stderr)
            return 1
        for target in targets:
            if sync_target(repo_root, target):
                print(f"synced {target.name}: {target.skill_path}")
        return 0

    if args.action == "reconcile-agents":
        dirs: list[tuple[str, Path, str | None]] = []
        for target in targets:
            if target.agents_dir:
                dirs.append((target.name, target.agents_dir, target.name))
        for raw_dir in args.agent_dir:
            path = Path(raw_dir).expanduser()
            dirs.append((str(path), path, None))
        if not dirs:
            print("No agent directories configured or passed with --agent-dir", file=sys.stderr)
            return 1
        for index, (label, path, host) in enumerate(dirs):
            if index:
                print("")
            print(format_agent_inventory_report(label, reconcile_agent_inventory(repo_root, path, host)))
        return 0

    if args.action == "sync-agents":
        if not args.agent_dir:
            print("Pass at least one --agent-dir for sync-agents", file=sys.stderr)
            return 1
        for raw_dir in args.agent_dir:
            path = Path(raw_dir).expanduser()
            sync_agents_dir(repo_root, path)
            print(f"synced agents: {path}")
        return 0

    if args.action == "bench":
        return run_bench(repo_root, args.bench_args, args.host, targets)

    if args.action == "print-cron":
        print(cron_line(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-anacron":
        print(anacron_line(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-launchd":
        print(launchd_plist(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-windows-task":
        print(windows_task_command(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-windows-xml":
        print(windows_task_xml(repo_root, python_bin=python_bin))
        return 0

    if args.action == "write-launchd":
        output = resolve_output_path(
            args.output,
            repo_root / ".runs" / "com.metazen11.autonomous-prompt-pack-sync.plist",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(launchd_plist(repo_root, python_bin=python_bin))
        print(output)
        return 0

    if args.action == "write-windows-xml":
        output = resolve_output_path(
            args.output,
            repo_root / ".runs" / "autonomous-prompt-pack-sync.xml",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(windows_task_xml(repo_root, python_bin=python_bin), encoding="utf-16")
        print(output)
        return 0

    if args.action == "install-git-hooks":
        written = install_git_hooks(repo_root, python_bin=python_bin)
        for hook_path in written:
            print(f"installed {hook_path}")
        return 0

    if not targets:
        print("No host targets configured in .env", file=sys.stderr)
        return 1

    if args.action == "sync":
        for target in targets:
            if sync_target(repo_root, target):
                print(f"synced {target.name}: {target.skill_path}")
        return 0

    failed = False
    for target in targets:
        status = check_target(repo_root, target)
        agents_status = "ok" if not status.missing_agents else ",".join(status.missing_agents)
        schemas_status = "n/a" if status.missing_schemas is None else ("ok" if not status.missing_schemas else ",".join(status.missing_schemas))
        scripts_status = "n/a" if status.missing_scripts is None else ("ok" if not status.missing_scripts else ",".join(status.missing_scripts))
        skill_status = format_status(status.skill_in_sync)
        instructions_status = format_status(status.instructions_in_sync)
        config_status = format_status(status.config_snippet_in_sync)
        bench_status = "n/a" if status.bench is None else (
            f"{len(status.bench)} ok" if not status.bench_problems else ",".join(status.bench_problems)
        )
        print(
            f"{target.name}: skill={skill_status} instructions={instructions_status} "
            f"config={config_status} agents={agents_status} bench={bench_status} "
            f"schemas={schemas_status} scripts={scripts_status}"
        )
        if (
            status.skill_in_sync is False
            or status.instructions_in_sync is False
            or status.config_snippet_in_sync is False
            or status.missing_agents
            or status.bench_problems
            or status.missing_schemas
            or status.missing_scripts
        ):
            failed = True
    return 1 if failed else 0


def run_bench(repo_root: Path, bench_args: list[str], hosts: list[str], targets) -> int:
    if bench_args == ["list"]:
        config = json.loads((repo_root / HOST_AGENTS_CONFIG).read_text()) if (repo_root / HOST_AGENTS_CONFIG).exists() else {}
        for host in hosts or [key for key in config if key in HOST_NAMES]:
            print(f"{host}: {', '.join(s.stem for s in host_bench_sources(repo_root, host)) or '(empty)'}")
        return 0
    if len(bench_args) != 2 or bench_args[0] not in ("play", "sit"):
        print("usage: sync_prompt_pack.py bench list | play NAME | sit NAME [--host HOST]", file=sys.stderr)
        return 2
    verb, name = bench_args
    try:
        changed = set_bench(repo_root, name, benched=verb == "sit", hosts=hosts or None)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if not changed:
        print(f"{name} already {'benched' if verb == 'sit' else 'active'}; nothing changed")
        return 0
    print(f"{'sat' if verb == 'sit' else 'played'} {name}: {', '.join(changed)}")
    for target in targets:
        if target.name in changed and sync_target(repo_root, target):
            print(f"synced {target.name}: {target.agents_dir}")
    unsynced = sorted(set(changed) - {target.name for target in targets})
    if unsynced:
        print(f"not configured in .env, not synced: {', '.join(unsynced)}")
    return 0


def resolve_output_path(raw_output: str | None, default_path: Path) -> Path:
    if raw_output is None:
        return default_path
    output = Path(raw_output)
    if not output.is_absolute():
        return Path.cwd() / output
    return output


def format_status(status: bool | None) -> str:
    if status is None:
        return "n/a"
    return "ok" if status else "stale"


if __name__ == "__main__":
    raise SystemExit(main())
