"""One production entrypoint: validate configuration, migrate, then serve."""

import os

import uvicorn
from alembic import command
from alembic.config import Config

from app.config import settings


def main():
    settings.validate_production()
    command.upgrade(Config("alembic.ini"), "head")
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), proxy_headers=False)


if __name__ == "__main__":
    main()
