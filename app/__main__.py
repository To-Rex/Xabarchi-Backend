"""Production entrypoint: ``python -m app``.

Applies pending Alembic migrations, then serves on ``0.0.0.0:{PORT}``
(``PORT`` comes from the environment or .env, default 8000). This is what
Dokploy/Railpack runs via railpack.json — and the same command works locally.
"""

from __future__ import annotations

import subprocess
import sys

import uvicorn

from app.core.config import settings


def main() -> None:
    # Migrations first: a boot with an out-of-date schema must not serve.
    # A failure exits non-zero so the orchestrator restarts/reports the deploy.
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
