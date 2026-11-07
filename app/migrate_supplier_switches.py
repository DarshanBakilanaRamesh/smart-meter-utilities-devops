"""Offline, additive SQLite migration. Run with the API stopped."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from sqlalchemy import inspect

from app import models  # noqa: F401 -- register all tables with Base.metadata
from app.database import Base, engine


def migrate(database_engine):
    if database_engine.dialect.name != "sqlite":
        raise RuntimeError("This migration supports SQLite only")
    database_path = database_engine.url.database
    if not database_path or database_path == ":memory:" or not Path(database_path).is_file():
        raise RuntimeError("Migration requires an existing SQLite database file")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = Path(f"{database_path}.{stamp}.{uuid4().hex}.bak")
    # Reserve a new filename; never overwrite another backup.
    with backup_path.open("xb"):
        pass
    source = database_engine.raw_connection()
    try:
        with closing(sqlite3.connect(backup_path)) as backup:
            source.driver_connection.backup(backup)
    finally:
        source.close()

    with database_engine.connect() as connection:
        # Explicit BEGIN makes SQLite DDL transactional, including ALTER TABLE.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            inspector = inspect(connection)
            if inspector.has_table("meters") and "current_supplier" not in {
                column["name"] for column in inspector.get_columns("meters")
            }:
                connection.exec_driver_sql(
                    "ALTER TABLE meters ADD COLUMN current_supplier "
                    "VARCHAR(120) NOT NULL DEFAULT 'DEFAULT'"
                )
            Base.metadata.create_all(bind=connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return backup_path


if __name__ == "__main__":
    try:
        print(f"Migration complete. Backup: {migrate(engine)}")
    finally:
        engine.dispose()
