#!/usr/bin/env python3
"""Repository-scoped lock for serializing reconcile operations."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LOCK_NAME = "reconcile.lock"
OWNER_FILE = "owner.json"
REQUIRED_FIELDS = {
    "schema",
    "task_id",
    "branch",
    "checkout",
    "host",
    "pid",
    "created_at",
}


class LockError(RuntimeError):
    """A lock operation cannot safely proceed."""


def _git(cwd: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise LockError(f"Cannot resolve Git state: {detail.strip()}") from exc
    return completed.stdout.strip()


def _git_paths(cwd: Path) -> tuple[Path, Path]:
    root = Path(_git(cwd, "rev-parse", "--show-toplevel")).resolve()
    try:
        common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    except LockError:
        relative = Path(_git(root, "rev-parse", "--git-common-dir"))
        common = relative if relative.is_absolute() else root / relative
    common = common.resolve()
    if not common.is_dir():
        raise LockError(f"Git common directory is unavailable: {common}")
    return root, common


def _read_owner(lock_dir: Path) -> dict[str, Any]:
    lock_fd = _open_lock_dir(lock_dir)
    try:
        return _read_owner_from_fd(lock_fd, lock_dir)
    finally:
        os.close(lock_fd)


def _open_lock_dir(lock_dir: Path) -> int:
    """Open a real lock directory without following a substituted symlink."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise LockError("This platform cannot safely open reconcile lock paths")
    try:
        fd = os.open(lock_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise LockError(f"Lock path is unavailable or is not a real directory: {lock_dir}") from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise LockError(f"Lock path is not a real directory: {lock_dir}")
    return fd


def _read_owner_from_fd(lock_fd: int, lock_dir: Path) -> dict[str, Any]:
    owner_path = lock_dir / OWNER_FILE
    if not hasattr(os, "O_NOFOLLOW"):
        raise LockError("This platform cannot safely open reconcile owner paths")
    try:
        owner_fd = os.open(
            OWNER_FILE,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=lock_fd,
        )
        with os.fdopen(owner_fd, "r", encoding="utf-8") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise LockError(f"Lock owner is not a regular file: {owner_path}")
            owner = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LockError(f"Lock state is unknown or malformed at {owner_path}") from exc
    if not isinstance(owner, dict) or not REQUIRED_FIELDS.issubset(owner):
        raise LockError(f"Lock state is unknown or malformed at {owner_path}")
    if owner.get("schema") != 1 or not all(
        isinstance(owner.get(key), str) and owner[key]
        for key in ("task_id", "branch", "checkout", "host", "created_at")
    ) or not isinstance(owner.get("pid"), int) or isinstance(owner.get("pid"), bool):
        raise LockError(f"Lock state is unknown or malformed at {owner_path}")
    return owner


def _status(common: Path) -> int:
    lock_dir = common / LOCK_NAME
    if not os.path.lexists(lock_dir):
        print("(no lock)")
        return 0
    try:
        owner = _read_owner(lock_dir)
    except LockError as exc:
        print(f"LOCK UNKNOWN: {exc}", file=sys.stderr)
        return 2
    print("LOCK ACTIVE")
    print(json.dumps(owner, sort_keys=True))
    return 0


def _verify_assignment(cwd: Path, expected_checkout: str, expected_branch: str) -> tuple[Path, str, Path]:
    root, common = _git_paths(cwd)
    assigned_checkout = Path(expected_checkout)
    if not assigned_checkout.is_absolute() or assigned_checkout.resolve() != root:
        raise LockError(f"Assigned checkout mismatch: expected {assigned_checkout}, running in {root}")
    branch = _git(root, "branch", "--show-current")
    if not expected_branch or branch != expected_branch:
        raise LockError(f"Assigned branch mismatch: expected {expected_branch or '(empty)'}, found {branch or 'detached HEAD'}")
    if branch in {"main", "master", "dev", "develop"}:
        raise LockError(f"Refusing to reconcile from a trunk branch: {branch}")
    return root, branch, common


def acquire(task_id: str, expected_checkout: str, expected_branch: str, cwd: Path) -> int:
    if not task_id or any(char in task_id for char in "\r\n\x00"):
        print("REFUSING: task id must be a non-empty single line", file=sys.stderr)
        return 2
    try:
        root, branch, common = _verify_assignment(cwd, expected_checkout, expected_branch)
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        print(f"REFUSING: assigned checkout is dirty: {root}", file=sys.stderr)
        return 2

    lock_dir = common / LOCK_NAME
    try:
        os.mkdir(lock_dir, 0o700)
    except FileExistsError:
        _status(common)
        print("Cannot acquire reconcile lock: another or unknown reconcile state exists.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Cannot create reconcile lock at {lock_dir}: {exc}", file=sys.stderr)
        return 2

    owner = {
        "schema": 1,
        "task_id": task_id,
        "branch": branch,
        "checkout": str(root),
        "host": socket.gethostname(),
        "pid": os.getpid(),  # audit metadata only; it is not used to clear a lock
        "created_at": datetime.now(UTC).isoformat(),
    }
    temp_path: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=".owner-", dir=lock_dir)
        temp_path = Path(name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(owner, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, lock_dir / OWNER_FILE)
        print("LOCK ACQUIRED")
        return 0
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        (lock_dir / OWNER_FILE).unlink(missing_ok=True)
        lock_dir.rmdir()
        print(f"Cannot write reconcile lock owner record: {exc}", file=sys.stderr)
        return 2


def release(task_id: str, expected_checkout: str, expected_branch: str, cwd: Path) -> int:
    try:
        root, branch, common = _verify_assignment(cwd, expected_checkout, expected_branch)
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    lock_dir = common / LOCK_NAME
    try:
        lock_fd = _open_lock_dir(lock_dir)
    except LockError as exc:
        print(f"Cannot release reconcile lock: {exc}", file=sys.stderr)
        return 2
    try:
        owner = _read_owner_from_fd(lock_fd, lock_dir)
        if owner["host"] != socket.gethostname():
            print("Cannot release reconcile lock: the recorded owner is on another host; liveness cannot be verified.", file=sys.stderr)
            return 1
        if (owner["task_id"], owner["checkout"], owner["branch"]) != (task_id, str(root), branch):
            print("Cannot release reconcile lock: task, checkout, or branch does not match the recorded owner.", file=sys.stderr)
            return 1
        entries = set(os.listdir(lock_fd))
        if entries != {OWNER_FILE}:
            print("Cannot release reconcile lock: unexpected lock contents; state preserved.", file=sys.stderr)
            return 2
        os.unlink(OWNER_FILE, dir_fd=lock_fd)
        lock_dir.rmdir()
    except OSError as exc:
        print(f"Cannot release reconcile lock safely: {exc}", file=sys.stderr)
        return 2
    except LockError as exc:
        print(f"Cannot release reconcile lock safely: {exc}", file=sys.stderr)
        return 2
    finally:
        os.close(lock_fd)
    print("LOCK RELEASED")
    return 0


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "status"
    cwd = Path.cwd()
    try:
        if action == "status" and len(argv) == 1:
            _, common = _git_paths(cwd)
            return _status(common)
        if action == "acquire" and len(argv) == 4:
            return acquire(argv[1], argv[2], argv[3], cwd)
        if action == "release" and len(argv) == 4:
            return release(argv[1], argv[2], argv[3], cwd)
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        "Usage: reconcile_lock.sh status | acquire <task-id> <assigned-checkout> <assigned-branch> "
        "| release <task-id> <assigned-checkout> <assigned-branch>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
