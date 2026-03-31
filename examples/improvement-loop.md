# Improvement Loop Example

If a DEV or TEST sequence succeeds repeatedly, the runtime can promote it into:

- a lesson in `agentMemory`
- a follow-up issue
- a playbook candidate
- a script candidate

Current runtime example:

- successful `DEV` command becomes a script candidate
- successful build/test chain becomes a playbook candidate

Local vs shared:

- local: `.autonomous-state.json`, `artifacts/`, `.runs/`, host install paths
- shared: GitHub Issues, committed prompt pack, committed runtime code
- durable but external: `agentMemory`
