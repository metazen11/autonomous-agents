# `agentMemory` Example

## Prerequisites

- local `agentMemory` service running and reachable
- runtime configured to reach that service, typically via the default local URL or explicit `--memory-url`

Validate the live local memory seam:

```bash
PYTHONPATH=. python3 scripts/validate_agent_memory.py --project-path .
```

Expected validated capabilities:

- health
- create lesson
- list lessons
- match lessons
- search observations
