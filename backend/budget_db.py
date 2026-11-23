import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

DEMO_PROJECT_ID = "demo-project"
STANDARD_CATEGORIES = {
    "personnel": "Personalkosten",
    "material": "Sachkosten",
    "other": "Sonstiges",
}


def table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def initialize_schema(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE planning_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE annual_plans (
            year INTEGER NOT NULL,
            category_id TEXT NOT NULL REFERENCES planning_categories (id),
            cents INTEGER NOT NULL,
            PRIMARY KEY (year, category_id)
        )
    """)
    db.executemany(
        "INSERT INTO planning_categories (id, name) VALUES (?, ?)",
        STANDARD_CATEGORIES.items(),
    )

    if table_exists(db, "budget_nodes"):
        # Copy only a standalone plan. A prior hierarchy stays in its original tables.
        if db.execute(
            "SELECT 1 FROM budget_nodes WHERE parent_id = ?", (DEMO_PROJECT_ID,)
        ).fetchone() is None:
            db.execute("""
                INSERT INTO planning_categories (id, name)
                SELECT id, name FROM budget_categories WHERE node_id = ?
                ON CONFLICT (id) DO UPDATE SET name = excluded.name
            """, (DEMO_PROJECT_ID,))
            db.execute("""
                INSERT INTO annual_plans (year, category_id, cents)
                SELECT year, category_id, cents FROM budget_plans WHERE node_id = ?
            """, (DEMO_PROJECT_ID,))
    elif table_exists(db, "project_budgets"):
        for category_id in STANDARD_CATEGORIES:
            db.execute(f"""
                INSERT INTO annual_plans (year, category_id, cents)
                SELECT year, ?, {category_id}_cents FROM project_budgets WHERE project_id = ?
            """, (category_id, DEMO_PROJECT_ID))


@contextmanager
def budget_db(*, write: bool = False):
    default_path = Path(__file__).resolve().with_name("budgets.sqlite3")
    with closing(sqlite3.connect(os.environ.get("BUDGET_DB_PATH") or default_path)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        if not table_exists(db, "annual_plans"):
            db.execute("BEGIN IMMEDIATE")
            if not table_exists(db, "annual_plans"):
                initialize_schema(db)
        elif write:
            db.execute("BEGIN IMMEDIATE")
        yield db
