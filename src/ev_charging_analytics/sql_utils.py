from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine


def run_sql_file(engine: Engine, path: Path) -> None:
    """Execute a SQL file containing semicolon-terminated PostgreSQL statements."""
    sql_text = path.read_text(encoding="utf-8")
    statements = [
        statement.strip()
        for statement in sql_text.split(";")
        if statement.strip() and not statement.strip().startswith("-- portfolio-only")
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)

