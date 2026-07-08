# Failure Recovery Report

## 1. Failure Scenarios

| Scenario | Behavior | Result |
|----------|----------|--------|
| Provider Timeout | Logged, returns 503 or Partial Success | PASS |
| DB Unavailable | Service reports degraded in health check | PASS |
| Invalid Token | Provider logged as 'Incomplete', excluded from scheduling | PASS |
| Network Split | Worker retries with exponential backoff | PASS |

## 2. Recovery Logic

- **Automatic Recovery**: Lifespan manager restarts the verification worker on crash.
- **Data Safety**: No local state; all metadata persisted in the database.
