from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.github import GitHubAdapter


class GitHubAdapterNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.script_path = Path(self.tmpdir.name) / "fake_gh.py"
        self.script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json, sys",
                    "args = sys.argv[1:]",
                    "if args[:3] == ['issue', 'list', '--state']:",
                    "    print(json.dumps([",
                    "        {'number': 12, 'title': 'High priority issue', 'body': '- [ ] add tests', 'labels': [{'name': 'priority:high'}], 'url': 'https://example/12'},",
                    "        {'number': 15, 'title': 'Blocked issue', 'body': '', 'labels': [{'name': 'blocked'}], 'url': 'https://example/15'}",
                    "    ]))",
                    "elif args[:2] == ['issue', 'view']:",
                    "    issue_id = args[2]",
                    "    print(json.dumps({'number': int(issue_id), 'title': f'Issue {issue_id}', 'body': '- [ ] verify', 'labels': [{'name': 'priority:urgent'}], 'url': f'https://example/{issue_id}'}))",
                    "elif args[:2] == ['issue', 'comment']:",
                    "    print('')",
                    "elif args[:2] == ['issue', 'create']:",
                    "    print(json.dumps({'number': 99, 'url': 'https://example/99'}))",
                    "else:",
                    "    raise SystemExit('unsupported args: ' + ' '.join(args))",
                ]
            )
            + "\n"
        )
        self.script_path.chmod(0o755)
        self.adapter = GitHubAdapter(
            repo_root=self.tmpdir.name,
            gh_command=["python3", str(self.script_path)],
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_list_ready_tasks_filters_skip_labels_and_maps_priority(self) -> None:
        tasks = self.adapter.list_ready_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "12")
        self.assertEqual(tasks[0].priority, "high")
        self.assertEqual(tasks[0].acceptance_criteria, ["add tests"])

    def test_get_task_maps_issue(self) -> None:
        task = self.adapter.get_task("42")
        self.assertEqual(task.id, "42")
        self.assertEqual(task.priority, "urgent")
        self.assertEqual(task.acceptance_criteria, ["verify"])

    def test_create_follow_up_returns_issue_number(self) -> None:
        issue_id = self.adapter.create_follow_up(
            item=type(
                "Candidate",
                (),
                {
                    "title": "Promote repeated checks",
                    "description": "Automate a stable command chain",
                    "expected_benefit": "fewer manual commands",
                    "source_evidence": ["run-1", "run-2"],
                },
            )()
        )
        self.assertEqual(issue_id, "99")


class GitHubAdapterCreateItemTest(unittest.TestCase):
    """Verify create_item builds the correct gh issue create invocation."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.args_log = Path(self.tmpdir.name) / "args.json"
        self.script_path = Path(self.tmpdir.name) / "fake_gh_create.py"
        # Script writes received args to args_log, then returns a fixed response.
        self.script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json, sys",
                    "args = sys.argv[1:]",
                    f"open({str(self.args_log)!r}, 'w').write(json.dumps(args))",
                    "if args[:2] == ['issue', 'create']:",
                    # Real `gh issue create` prints the new issue URL on stdout;
                    # it does not support --json. Match that contract.
                    "    print('https://github.com/acme/widgets/issues/42')",
                    "else:",
                    "    raise SystemExit('unsupported: ' + ' '.join(args))",
                ]
            )
            + "\n"
        )
        self.script_path.chmod(0o755)
        self.adapter = GitHubAdapter(
            repo_root=self.tmpdir.name,
            gh_command=["python3", str(self.script_path)],
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_create_item_returns_number_and_url(self) -> None:
        number, url = self.adapter.create_item(
            title="My task",
            body="intent text",
            criteria=["crit one", "crit two"],
            labels=["lane:etl", "priority:high"],
        )
        self.assertEqual(number, "42")
        self.assertEqual(url, "https://github.com/acme/widgets/issues/42")
        # Regression guard: `gh issue create` must NOT be called with --json,
        # which the real CLI rejects as an unknown flag.
        args = json.loads(self.args_log.read_text())
        self.assertNotIn("--json", args)

    def test_create_item_includes_criteria_as_checklist_in_body(self) -> None:
        self.adapter.create_item(
            title="My task",
            body="intent text",
            criteria=["crit one", "crit two"],
            labels=["lane:etl"],
        )
        args = json.loads(self.args_log.read_text())
        # Locate the --body value
        body_idx = args.index("--body")
        body_value = args[body_idx + 1]
        self.assertIn("- [ ] crit one", body_value)
        self.assertIn("- [ ] crit two", body_value)

    def test_create_item_passes_labels_via_flag(self) -> None:
        self.adapter.create_item(
            title="My task",
            body="intent",
            criteria=[],
            labels=["lane:etl", "priority:high"],
        )
        args = json.loads(self.args_log.read_text())
        # Each label must appear as --label <value>
        label_values = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
        self.assertIn("lane:etl", label_values)
        self.assertIn("priority:high", label_values)

    def test_create_item_no_criteria_omits_checklist(self) -> None:
        self.adapter.create_item(
            title="My task",
            body="intent only",
            criteria=[],
            labels=[],
        )
        args = json.loads(self.args_log.read_text())
        body_idx = args.index("--body")
        body_value = args[body_idx + 1]
        self.assertNotIn("- [ ]", body_value)
        self.assertEqual(body_value, "intent only")


if __name__ == "__main__":
    unittest.main()
