"""Create the explicitly selected local demo database, without altering existing data."""

import os
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

target = urlsplit(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1))
name = unquote(target.path.removeprefix("/"))
admin = urlunsplit(target._replace(path="/postgres"))
with psycopg.connect(admin, autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
print("explicit local database ready; existing data preserved")
