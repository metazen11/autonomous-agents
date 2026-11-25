from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_COMMAND = REPO_ROOT / "scripts/reconcile_lock.sh"


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


class ReconcileLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-b", "feature/test"], cwd=self.repo, check=True, capture_output=True)
        git(self.repo, "config", "user.name", "Test User")
        git(self.repo, "config", "user.email", "test@example.invalid")
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=self.repo, check=True, capture_output=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_lock(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(LOCK_COMMAND), *args],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def lock_path(self) -> Path:
        common = Path(git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        return common / "reconcile.lock"

    @property
    def assignment(self) -> tuple[str, str]:
        return str(self.repo.resolve()), "feature/test"

    def acquire(self, task_id: str) -> subprocess.CompletedProcess[str]:
        return self.run_lock("acquire", task_id, *self.assignment)

    def release(self, task_id: str) -> subprocess.CompletedProcess[str]:
        return self.run_lock("release", task_id, *self.assignment)

    def test_acquire_status_wrong_owner_and_release(self) -> None:
        acquired = self.acquire("GH-29")
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertNotIn("token", acquired.stdout.lower())
        self.assertEqual(self.lock_path().stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.lock_path() / "owner.json").stat().st_mode & 0o777, 0o600)

        status = self.run_lock("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('"task_id": "GH-29"', status.stdout)

        denied = self.release("GH-30")
        self.assertNotEqual(denied.returncode, 0)
        self.assertTrue(self.lock_path().is_dir())

        released = self.release("GH-29")
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(self.lock_path().exists())

    def test_assignment_mismatch_refuses_without_lock_creation(self) -> None:
        wrong_checkout = self.run_lock("acquire", "GH-29", str(self.repo / "elsewhere"), "feature/test")
        wrong_branch = self.run_lock("acquire", "GH-29", str(self.repo.resolve()), "feature/wrong")
        self.assertNotEqual(wrong_checkout.returncode, 0)
        self.assertIn("Assigned checkout mismatch", wrong_checkout.stderr)
        self.assertNotEqual(wrong_branch.returncode, 0)
        self.assertIn("Assigned branch mismatch", wrong_branch.stderr)
        self.assertFalse(self.lock_path().exists())

    def test_concurrent_acquire_grants_one_owner(self) -> None:
        processes = [
            subprocess.Popen(
                ["bash", str(LOCK_COMMAND), "acquire", f"GH-{index}", *self.assignment],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for index in range(2)
        ]
        results = [process.communicate(timeout=10) + (process.returncode,) for process in processes]
        self.assertEqual(sorted(result[2] for result in results), [0, 1])
        status = self.run_lock("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        task_id = json.loads(status.stdout.splitlines()[1])["task_id"]
        released = self.release(task_id)
        self.assertEqual(released.returncode, 0, released.stderr)

    def test_malformed_lock_fails_closed_without_worktree_change(self) -> None:
        lock = self.lock_path()
        lock.mkdir(mode=0o700)
        (lock / "owner.json").write_text("not json\n", encoding="utf-8")
        before = git(self.repo, "worktree", "list", "--porcelain")

        status = self.run_lock("status")
        acquire = self.acquire("GH-29")
        after = git(self.repo, "worktree", "list", "--porcelain")

        self.assertEqual(status.returncode, 2)
        self.assertNotEqual(acquire.returncode, 0)
        self.assertIn("LOCK UNKNOWN", status.stderr)
        self.assertEqual(before, after)
        self.assertEqual((lock / "owner.json").read_text(encoding="utf-8"), "not json\n")

    def test_stale_and_unknown_host_locks_are_not_cleared_automatically(self) -> None:
        acquired = self.acquire("GH-29")
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        lock = self.lock_path()
        owner_path = lock / "owner.json"
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        owner["pid"] = 99999999
        owner["host"] = "unreachable-host"
        owner_path.write_text(json.dumps(owner), encoding="utf-8")
        before = git(self.repo, "worktree", "list", "--porcelain")

        status = self.run_lock("status")
        denied = self.acquire("GH-30")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('"host": "unreachable-host"', status.stdout)
        self.assertNotEqual(denied.returncode, 0)
        self.assertTrue(lock.is_dir())
        self.assertEqual(before, git(self.repo, "worktree", "list", "--porcelain"))

    def test_dirty_assigned_checkout_refuses_before_lock_creation(self) -> None:
        (self.repo / "uncommitted.txt").write_text("preserve me\n", encoding="utf-8")
        before = git(self.repo, "worktree", "list", "--porcelain")

        result = self.acquire("GH-29")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assigned checkout is dirty", result.stderr)
        self.assertFalse(self.lock_path().exists())
        self.assertEqual(before, git(self.repo, "worktree", "list", "--porcelain"))
        self.assertEqual((self.repo / "uncommitted.txt").read_text(encoding="utf-8"), "preserve me\n")


if __name__ == "__main__":
    unittest.main()
