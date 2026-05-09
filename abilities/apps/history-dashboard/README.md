# History Dashboard Ability

This ability exposes the Robin history dashboard as a Next.js app.
The checked-in `./bin/history-dashboard` shim runs the production app in Docker
by default.

## Commands

```bash
./bin/history-dashboard help
./bin/history-dashboard status
./bin/history-dashboard serve
./bin/history-dashboard serve --background
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
- `serve` starts the production Next.js server in a foreground Docker container.
- `serve --background` starts it as the detached `robin-history-dashboard` Docker container. Stop it with `docker stop robin-history-dashboard`.
- The first Dockerized run builds the `robin-history-dashboard` image if it is missing.
- `ROBIN_HOME` is mounted read-only at `/robin-home` inside the container.
- The dashboard is read-only and shows cross-service run history plus run logs.
- If `HISTORY_DASHBOARD_AUTH_USERNAME` and `HISTORY_DASHBOARD_AUTH_PASSWORD` are both set, the app requires HTTP Basic Auth.
- If either auth variable is empty or unset, auth is disabled (open access fallback).
