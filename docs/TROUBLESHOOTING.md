# Troubleshooting

## `docker compose up` fails with "port is already allocated"
Another process is using 5432 (Postgres) or 5678 (n8n). Stop the conflicting process or change the port in `.env` (`POSTGRES_PORT`, `N8N_PORT`) and re-run `./scripts/demo_start.sh`.

## `pg_isready` never succeeds
Docker Desktop may not be running. Start it and retry. On Windows, confirm WSL 2 integration is enabled.

## `migrate.py` errors with `could not connect to server`
Either Postgres isn't up yet (wait and retry), or `.env` has the wrong `POSTGRES_HOST`/`POSTGRES_PORT`. From the host, `POSTGRES_HOST` should be `localhost`.

## FastAPI log says `ModuleNotFoundError: services`
You're running uvicorn from the wrong directory. `demo_start.sh` runs it from the repo root, which is required — `services` is a package rooted there.

## n8n can't reach the API at `localhost:8000`
Inside the n8n container, use `http://host.docker.internal:8000` instead of `localhost`. The docker-compose file already adds the required `extra_hosts` entry.

## More coming as we hit them during Phases 2–7.
