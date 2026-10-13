# Secret Rotator — agent role SPEC (draft, not yet a contract)

Status: **idea captured, not implemented.** Belongs in the canonical prompt pack
(this repo), rendered to hosts like the other `aa_*` roles. Global/cross-project,
not per-repo.

## Why (the pain that motivated it — fire-map 2026-06-30 → 07-04)

A DB credential rotation left a trail of failure modes that a disciplined rotator
would have prevented:

1. **Stale local copies.** Rotated the DB password in AWS Amplify, but
   `database/etl/config.json` and `.env.local` (both consumers) were never
   updated → `db.py` / `apply_schemas.py` failed auth for days. A secret lives
   in MANY places (Amplify env vars, config.json, .env.local, Lambda env, Docker
   image, Secrets Manager); rotating one and missing the rest is the default
   outcome without automation.
2. **Permission drift on the new credential.** The new role (`wfca_app`) was
   least-privilege (SELECT/USAGE only) while the old role (`postgres`) could
   CREATE/INSERT. Migrations/seeds silently broke because the *new secret did
   not have the SAME permissions* as the old. Nobody checked parity before the
   old one was effectively retired.
3. **No archive/rollback trail.** No versioned record of the prior secret to
   fall back to, and no discipline of "don't delete the old until the new is
   proven."
4. **Leak risk on the rewrite.** `config.json` is git-TRACKED — writing the
   rotated cred into it risks committing a live secret (the original 2026-06-30
   incident's root cause). Any rotator that writes local files must know which
   are tracked and never leave a secret in a committable file.

## Core contract (operator's stated requirements)

- **Versioned archive naming:** `secret_name` → `secret_name_archived_1`, `_2`,
  … so archived versions are tracked for eventual deletion and reachable if
  needed before deletion.
- **Never delete the old secret until the new one is confirmed working** — and
  specifically **with the SAME permissions** as the old. Permission-parity is a
  hard gate, not advisory. (This is the exact bug above.)
- Verify-before-archive; keep the old reachable until confirmed.

## Candidate responsibilities (to confirm with operator — some cut off in convo)

- **Permission-parity verification** — prove the new credential can do
  everything the old could (grants/roles diff). Refuse to archive on mismatch
  unless the diff is explicitly approved.
- **Propagate to ALL consumers atomically** — enumerate every place the secret
  lives (Amplify app+branch env vars, SSM, Lambda env, config.json, .env.local,
  Docker build args, Secrets Manager) and update + connectivity-verify each; no
  stale copy left.
- **Scheduled rotation** (e.g. 90d) with the same verify-before-archive safety,
  not just on-incident.
- **Audit trail + rollback** — log ts/actor/reason; `rollback <secret> --to vN`.

## Open design decision (not yet made)

**Where do secrets LIVE as source of truth?**
- (A) Migrate to **AWS Secrets Manager** — native rotation + versioning already
  exists there via staging labels `AWSCURRENT`/`AWSPREVIOUS` (the operator's
  `_archived_1/_2` idea is literally AWSPREVIOUS). Consumers read at runtime via
  IAM. Biggest change, best end state. Already flagged as a follow-up in
  fire-map memory (`project_secrets_manager_migration`). Note the rotator would
  then largely orchestrate Secrets Manager rotation lambdas + the
  consumer-propagation + parity-check that SM does NOT do for you.
- (B) Keep current stores (Amplify env vars, config.json, Lambda env) and build
  the rotator to orchestrate + verify across the sprawl. Less migration, keeps
  multiple copies to sync.

Recommendation to develop later: **A** for the store (SM gives you archive +
rollback for free via staging labels), with the rotator adding the two things SM
does NOT do — **cross-consumer propagation** and **permission-parity gating** —
which are exactly the two failures that bit fire-map.

## Hard rules for whoever implements

- MUST detect git-tracked config files and NEVER leave a secret value in a
  committable file (write, use, restore — or better, don't write to tracked
  files at all).
- MUST NOT print secret values to logs/terminal (presence-only reporting).
- MUST verify the new secret end-to-end (connect + permission parity) BEFORE
  archiving the old, and keep the old reachable until confirmed.
- Ties to fire-map `reference_dev_db_creds_location` +
  `project_db_cred_leak_2026_06_30` + `project_secrets_manager_migration` for
  the concrete case that motivated this.

## TODO before this becomes a real `aa_secret_rotator` contract

- Confirm the cut-off "It would also use ___" responsibility with the operator.
- Pick store (A vs B).
- Define the Inputs/Output schema + permission-parity check mechanism per store
  type (Postgres role grants, IAM policy, etc.).
- Render via `scripts/sync_prompt_pack.py` once graduated from SPEC → contract.
