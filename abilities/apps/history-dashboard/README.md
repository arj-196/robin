# History Dashboard Ability

This ability exposes the Robin history dashboard as a Next.js app.

## Commands

```bash
./bin/history-dashboard help
./bin/history-dashboard status
./bin/history-dashboard serve
```

## Environment

```bash
HISTORY_DASHBOARD_PORT=3000
HISTORY_DASHBOARD_HISTORY_LIMIT=500
HISTORY_DASHBOARD_AUTH_USERNAME=
HISTORY_DASHBOARD_AUTH_PASSWORD=
ROBIN_HOME=.robin
ROBIN_RUN_LEDGER_DIR=run-ledger
ROBIN_LOG_RUNS_DIR=logs
```

## Notes

- `status` prints a lightweight health payload.
- `serve` starts a local Next.js web app from `abilities/apps/history-dashboard/web`.
- Install frontend dependencies first: `cd abilities/apps/history-dashboard/web && npm install`.
- The dashboard is read-only and shows cross-service run history plus run logs.
- If `HISTORY_DASHBOARD_AUTH_USERNAME` and `HISTORY_DASHBOARD_AUTH_PASSWORD` are both set, the app requires HTTP Basic Auth.
- If either auth variable is empty or unset, auth is disabled (open access fallback).
