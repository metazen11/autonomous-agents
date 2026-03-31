# agentMemory Integration

The runtime treats `agentMemory` as the durable learning layer.

## Current Contract

Validated local contract:

- health via `/api/health`
- lesson create via `/api/lessons`
- lesson list via `/api/lessons`
- lesson match via `/api/lessons/match`
- observation search via `/api/observations/search`

## Runtime Use

- `INIT`
  Load project-scoped lessons and record memory availability.
- `IMPROVE`
  Persist durable lessons and promotion candidates.
- validation
  `scripts/validate_agent_memory.py`

## Policy

- raw run logs belong in artifacts, not memory
- memory stores durable lessons, patterns, and promoted playbooks
- the runtime must degrade cleanly when `agentMemory` is unavailable

