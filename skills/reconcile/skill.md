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
3. **Private checkout.** `git fetch origin`, then work in a throwaway detached worktree at the branch tip. Never move a shared checkout's HEAD. Before rewriting anything, tag the tip `backup/reconcile-<branch>`.
4. **Rebase** onto `origin/<integration>`. A conflict you do not fully understand: STOP and report the files. Never `-X theirs/ours` to get through it.
5. **Squash** to one commit: `git reset --soft origin/<integration> && git commit` with the branch's purpose as the message.
6. **Gate** on that exact commit, using what the repo's instruction files define. Red: STOP, nothing is pushed. If `tools/suite_lane.py` exists: `python tools/suite_lane.py run --base <integration sha> --trailer-out <file>`, then append that file to the commit message with `git commit --amend`.
7. **Push** `git push origin HEAD:refs/heads/<integration>`, never forced, so a moved trunk is refused. Refused: go back to step 3 once, then STOP. Never skip hooks.
8. **Verify and clean up.** `git merge-base --is-ancestor HEAD origin/<integration>` after a fetch, then remove the throwaway worktree and report the sha. Keep the branch and backup tag unless the operator says otherwise.

Never push to the production trunk, use `--admin`, or open a feature PR from this flow.
