from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from autonomous_pipeline.specialists import execute_specialist, get_specialist_contract, list_specialist_contracts
from autonomous_pipeline.schemas import RunState, RuntimeConfig, Task


class SpecialistsTest(unittest.TestCase):
    def test_registry_contains_expected_core_contracts(self) -> None:
        names = [contract.name for contract in list_specialist_contracts()]
        self.assertIn("code-reviewer", names)
        self.assertIn("qa-tester", names)
        self.assertIn("skill-promoter", names)

    def test_bounded_write_contract_requires_scope(self) -> None:
        contract = get_specialist_contract("security-fixer")
        self.assertEqual(contract.mode, "bounded_write")
        self.assertTrue(contract.allowed_write_scope_required)

    def test_security_auditor_flags_sensitive_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_specialist(
                "security-auditor",
                repo_root=tmpdir,
                artifacts_root=tmpdir,
                task=Task(
                    id="1",
                    title="security",
                    metadata={"changed_files": ["src/auth/token_manager.py"]},
                ),
                run_state=RunState(session_id="s1", repo_root=tmpdir),
                config=RuntimeConfig(),
            )
            self.assertEqual(result.status, "success")
            self.assertTrue(result.findings)
            self.assertTrue(Path(result.artifacts[0]).exists())

    def test_db_analyst_flags_migration_without_data_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_specialist(
                "db-analyst",
                repo_root=tmpdir,
                artifacts_root=tmpdir,
                task=Task(
                    id="1",
                    title="db",
                    metadata={"changed_files": ["migrations/001_add_table.sql"]},
                ),
                run_state=RunState(session_id="s1", repo_root=tmpdir),
                config=RuntimeConfig(),
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.findings[0]["title"], "Database change lacks data verification")

    def test_infra_checker_needs_human_without_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_specialist(
                "infra-checker",
                repo_root=tmpdir,
                artifacts_root=tmpdir,
                task=Task(id="1", title="infra"),
                run_state=RunState(session_id="s1", repo_root=tmpdir),
                config=RuntimeConfig(),
            )
            self.assertEqual(result.status, "needs_human")

    def test_code_reviewer_pre_test_stage_does_not_require_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_specialist(
                "code-reviewer",
                repo_root=tmpdir,
                artifacts_root=tmpdir,
                task=Task(
                    id="1",
                    title="code review",
                    metadata={"changed_files": ["src/a.py"]},
                ),
                run_state=RunState(session_id="s1", repo_root=tmpdir),
                config=RuntimeConfig(),
                stage="CODE_REVIEW",
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.findings, [])

    def test_code_reviewer_flags_naming_style_concern(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_specialist(
                "code-reviewer",
                repo_root=tmpdir,
                artifacts_root=tmpdir,
                task=Task(
                    id="1",
                    title="style review",
                    metadata={"changed_files": ["bad file.py"], "verification_results": [{"category": "unit", "status": "pass", "command": "pytest"}]},
                ),
                run_state=RunState(session_id="s1", repo_root=tmpdir),
                config=RuntimeConfig(),
                stage="REVIEW",
            )
            self.assertEqual(result.status, "success")
            self.assertTrue(any(item["title"] == "Naming or style convention concern" for item in result.findings))


if __name__ == "__main__":
    unittest.main()
