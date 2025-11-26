# Staging Web App Baseline

This note captures the production EC2 web application footprint so staging instances can mirror it exactly. Update it whenever the prod host changes.

## Host Image
- **AMI family**: Ubuntu 22.04 LTS (verify with `lsb_release -a`).
- **Kernel / patch level**: `uname -a`.
- **AMI refresh**: After patching prod, create an AMI named `market-pulse-webapp-prod-<date>`; `infrastructure/webapp-staging` consumes that ID.

## System Packages
Record the versions below (use the commands in parentheses):

| Component | Version | Command |
|-----------|---------|---------|
| nginx | | `apt show nginx | grep Version` |
| Docker Engine | | `docker --version` |
| docker compose v2 | | `docker compose version` |
| uv | | `uv --version` |
| certbot | | `certbot --version` |

## Python Runtime
- `which uv` should be `/home/ubuntu/.local/bin/uv`.
- Export `uv pip list` to `infra/baseline/python-packages.txt` for auditing.
- Keep `pyproject.toml` + `uv.lock` committed so `uv sync --frozen` is reproducible.

## Application Service
Systemd unit lives at `/etc/systemd/system/market-pulse.service` (see [`docs/deployment.md`](deployment.md)). Capture it with:

```
sudo systemctl cat market-pulse > /opt/market-pulse-v2/docs/systemd-market-pulse.service
```

Key expectations:
- `WorkingDirectory=/opt/market-pulse-v2`
- `EnvironmentFile=/opt/market-pulse-v2/.env`
- `ExecStartPre=/usr/bin/docker compose up -d postgres`
- `ExecStart=/home/ubuntu/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Environment Variables
`/opt/market-pulse-v2/.env` must be identical to production secrets so staging points at the shared Postgres + APIs. Keep a sanitized reference in `infra/baseline/env.sample`. Keys today:

```
POSTGRES_URL=postgresql+psycopg://postgres:<pw>@<prod-host>:5432/market_pulse
OPENAI_API_KEY=...
FINNHUB_TOKEN=...
SENTIMENT_USE_LLM=true
SENTIMENT_FALLBACK_VADER=false
REDIS_URL=redis://localhost:6379/0
```

## Reverse Proxy
- `/etc/nginx/sites-available/market-pulse` proxies to `http://localhost:8000`.
- Certificates live in `/etc/letsencrypt/live/<domain>/`.
- Export the config for posterity:

```
sudo cat /etc/nginx/sites-available/market-pulse > /opt/market-pulse-v2/docs/nginx-market-pulse.conf
```

## Data & Logs
- App logs: `/var/log/market-pulse/*.log`.
- Postgres volume: Docker named volume `market-pulse-v2_postgres-data`.
- Dumps: `market_pulse_dump.sql` in repo.

## Verification Checklist
1. `systemctl status market-pulse`
2. `curl -f http://localhost:8000/health`
3. `docker compose ps postgres`
4. `redis-cli ping`
5. `nginx -t`
