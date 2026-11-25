---
name: reconcile
description: "Land a feature branch on the integration trunk (legacy two-trunk repos: fetch, rebase, gate, squash, push; no PR). Single-trunk repos go to the reconciler specialist instead."
argument-hint: "[branch] (default: current branch)"
user-invocable: true
---

# /reconcile: land a branch on the integration trunk

Contract: `docs/contract-reference.md` BR-10. Run one landing at a time per repo.

1. **Model.** `git show origin/<trunk>:.reconcile-gate.json` is exactly `{"model":"single-trunk"}`: dispatch `aa_reconciler` and stop here. Otherwise the integration trunk is `dev`, else `develop`; neither exists: STOP and ask, never create one.
2. **Preconditions.** Independent code review (§CR) is done with no open blocking finding, and an audit PASS exists when the work has an issue (§IP). Missing: get them, do not land.
3. **Use only the assigned checkout and acquire the lock.** The originating issue or dispatch must name the exact checkout and working branch. Record the checkout path, branch, HEAD, and `git status --porcelain`; proceed only when the branch matches and the tree is clean. Do not select a different clean-looking checkout or move another agent's/session's HEAD. If the assigned checkout is dirty, ownership is unclear, or the expected branch is absent, stop and report its exact state. Resolve the directory containing this loaded `/reconcile` skill and run its bundled `scripts/reconcile_lock.sh acquire <task-id> <assigned-checkout> <assigned-branch>` with the assigned checkout as the command's working directory; do not assume the helper exists inside the target repository. The command verifies the current path and branch match the assignment. If acquisition fails or lock state is malformed, stale, or unknown, stop without clearing it. Release with the same bundled helper using `scripts/reconcile_lock.sh release <task-id> <assigned-checkout> <assigned-branch>` after success or failure. The lock serializes reconciliation but does not authenticate the prompt author. Do not automatically run `git worktree add`. A new checkout is allowed only after an explicit owner request and a verified linked-worktree count below the hard cap of five, using the shared guard. Before rewriting anything, tag the tip `backup/reconcile-<branch>`.
4. **Rebase** onto `origin/<integration>`. A conflict you do not fully understand: STOP and report the files. Never `-X theirs/ours` to get through it.
5. **Squash** to one commit: `git reset --soft origin/<integration> && git commit` with the branch's purpose as the message.
6. **Gate** on that exact commit, using what the repo's instruction files define. Red: STOP, nothing is pushed. If `tools/suite_lane.py` exists: `python tools/suite_lane.py run --base <integration sha> --trailer-out <file>`, then append that file to the commit message with `git commit --amend`.
7. **Push** `git push origin HEAD:refs/heads/<integration>`, never forced, so a moved trunk is refused. If refused, keep the current lock; fetch, rebase onto the updated integration trunk, squash, and rerun the exact-commit gate once without reacquiring the lock. Retry the push once. If the second push is refused or any gate fails, release the lock and STOP with the exact blocker. Never skip hooks.
8. **Verify and release.** `git merge-base --is-ancestor HEAD origin/<integration>` after a fetch and report the landed SHA. Release with `scripts/reconcile_lock.sh release <task-id> <assigned-checkout> <assigned-branch>` on every normal success or failure path. If interrupted and the lock remains, do not clear it based on age or PID alone; first verify no reconcile is active, then use the documented manual recovery. Keep the branch and backup tag unless the operator says otherwise.

Never push to the production trunk, use `--admin`, or open a feature PR from this flow.
