"""Local PostgreSQL + pgvector for Windows development, without Docker or an installer.

Uses the `pgserver` package, which ships PostgreSQL binaries with pgvector built in.
Data lives in .local-postgres/ at the repository root.

    python scripts/local_db.py start    # start (if needed) and print the DATABASE_URL
    python scripts/local_db.py stop
"""

import sys
from pathlib import Path

import pgserver
import pgserver.postgres_server

DATA = Path(__file__).resolve().parent.parent / ".local-postgres"
DATABASES = ("chatbot", "chatbot_test")  # app and pytest
PORT = 55432  # fixed, so database tools (pgAdmin, DBeaver, VS Code) can save the connection

# pgserver normally picks a random free port on Windows; always use PORT instead.
pgserver.postgres_server.find_suitable_port = lambda address=None: PORT


def start():
    server = pgserver.get_server(str(DATA), cleanup_mode=None)  # keeps running after this script exits
    for name in DATABASES:
        if not server.psql(f"SELECT 1 FROM pg_database WHERE datname = '{name}';").count("(1 row)"):
            server.psql(f"CREATE DATABASE {name};")
    base = server.get_uri().rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://")
    print(base + "/chatbot")


def stop():
    if DATA.exists():
        pgserver.get_server(str(DATA), cleanup_mode="stop").cleanup()
    print("Local database stopped; data kept in .local-postgres")


if __name__ == "__main__":
    {"start": start, "stop": stop}[sys.argv[1] if len(sys.argv) > 1 else "start"]()
