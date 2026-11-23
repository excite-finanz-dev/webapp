import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints

DEMO_PROJECT_ID = "demo-project"
router = APIRouter(prefix=f"/api/projects/{DEMO_PROJECT_ID}/budgets", tags=["Project budgets"])

STANDARD_CATEGORIES = {
    "personnel": "Personalkosten",
    "material": "Sachkosten",
    "other": "Sonstiges",
}
BudgetYear = Annotated[int, ApiPath(ge=2000, le=2100)]
Cents = Annotated[int, Field(strict=True, ge=0, le=999_999_999_999)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class PlannedCosts(RootModel[dict[str, Cents]]):
    """Annual planned amounts in cents by stable cost category ID."""


class NamedBudgetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DisplayName


class NewBudgetNode(NamedBudgetItem):
    parent_id: str = DEMO_PROJECT_ID


class BudgetNode(BaseModel):
    id: str
    parent_id: str | None
    name: str


class CostCategory(BaseModel):
    id: str
    node_id: str
    name: str


class AnnualPlan(BaseModel):
    node_id: str
    year: int
    categories: list[CostCategory]
    planned_cents: PlannedCosts
    planned_total_cents: int


class LegacyPlannedCosts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personnel: Cents
    material: Cents
    other: Cents


class ProjectBudget(BaseModel):
    project_id: Literal["demo-project"] = DEMO_PROJECT_ID
    year: int
    planned_cents: LegacyPlannedCosts
    planned_total_cents: int


class BudgetLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_limit_cents: Cents


class CategorySummary(BaseModel):
    category: CostCategory
    planned_cents: int
    actual_cents: int | None = None


class BudgetOverview(BaseModel):
    project_id: Literal["demo-project"] = DEMO_PROJECT_ID
    year: int
    budget_limit_cents: int | None
    planned_total_cents: int
    unallocated_cents: int | None
    categories: list[CategorySummary]
    actual_status: Literal["not_reconciled"] = "not_reconciled"
    actual_total_cents: int | None = None


def table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def initialize_schema(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE budget_nodes (
            id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES budget_nodes (id),
            name TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE budget_categories (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES budget_nodes (id),
            name TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE budget_plans (
            node_id TEXT NOT NULL REFERENCES budget_nodes (id),
            year INTEGER NOT NULL,
            category_id TEXT NOT NULL REFERENCES budget_categories (id),
            cents INTEGER NOT NULL,
            PRIMARY KEY (node_id, year, category_id)
        )
    """)
    db.execute("CREATE INDEX budget_plans_by_year ON budget_plans (year, category_id)")
    db.execute("""
        CREATE TABLE project_budget_limits (
            project_id TEXT NOT NULL REFERENCES budget_nodes (id),
            year INTEGER NOT NULL,
            cents INTEGER NOT NULL,
            PRIMARY KEY (project_id, year)
        )
    """)
    db.execute(
        "INSERT INTO budget_nodes (id, name) VALUES (?, ?)",
        (DEMO_PROJECT_ID, "Demo-Projekt"),
    )
    db.executemany(
        "INSERT INTO budget_categories (id, node_id, name) VALUES (?, ?, ?)",
        [(category_id, DEMO_PROJECT_ID, name) for category_id, name in STANDARD_CATEGORIES.items()],
    )

    if table_exists(db, "project_budgets"):
        # The old table only recorded plans. Migrate them to the root node.
        for category_id in STANDARD_CATEGORIES:
            db.execute(
                f"""
                INSERT INTO budget_plans (node_id, year, category_id, cents)
                SELECT project_id, year, ?, {category_id}_cents
                FROM project_budgets WHERE project_id = ?
                """,
                (category_id, DEMO_PROJECT_ID),
            )


@contextmanager
def budget_db(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    default_path = Path(__file__).resolve().with_name("budgets.sqlite3")
    with closing(sqlite3.connect(os.environ.get("BUDGET_DB_PATH") or default_path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        if table_exists(db, "budget_nodes"):
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        else:
            db.execute("BEGIN IMMEDIATE")
            if not table_exists(db, "budget_nodes"):
                initialize_schema(db)
        yield db


def require_node(db: sqlite3.Connection, node_id: str) -> None:
    if db.execute("SELECT 1 FROM budget_nodes WHERE id = ?", (node_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Budgetebene nicht gefunden.")


def available_categories(db: sqlite3.Connection, node_id: str) -> list[CostCategory]:
    rows = db.execute(
        """
        WITH RECURSIVE ancestors (id, parent_id, distance) AS (
            SELECT id, parent_id, 0 FROM budget_nodes WHERE id = ?
            UNION ALL
            SELECT parent.id, parent.parent_id, ancestors.distance + 1
            FROM ancestors JOIN budget_nodes AS parent ON parent.id = ancestors.parent_id
        )
        SELECT category.id, category.node_id, category.name
        FROM ancestors JOIN budget_categories AS category ON category.node_id = ancestors.id
        ORDER BY ancestors.distance DESC, category.rowid
        """,
        (node_id,),
    )
    return [CostCategory(**dict(row)) for row in rows]


def stored_costs(db: sqlite3.Connection, node_id: str, year: int) -> dict[str, int]:
    return dict(db.execute(
        "SELECT category_id, cents FROM budget_plans WHERE node_id = ? AND year = ?",
        (node_id, year),
    ).fetchall())


def write_costs(db: sqlite3.Connection, node_id: str, year: int, costs: dict[str, int]) -> None:
    db.executemany(
        """
        INSERT INTO budget_plans (node_id, year, category_id, cents) VALUES (?, ?, ?, ?)
        ON CONFLICT (node_id, year, category_id) DO UPDATE SET cents = excluded.cents
        """,
        [(node_id, year, category_id, cents) for category_id, cents in costs.items()],
    )


def annual_plan(
    node_id: str, year: int, categories: list[CostCategory], costs: dict[str, int]
) -> AnnualPlan:
    amounts = {category.id: costs.get(category.id, 0) for category in categories}
    return AnnualPlan(
        node_id=node_id,
        year=year,
        categories=categories,
        planned_cents=PlannedCosts(amounts),
        planned_total_cents=sum(amounts.values()),
    )


@router.get("/nodes")
def list_nodes() -> list[BudgetNode]:
    with budget_db() as db:
        rows = db.execute("SELECT id, parent_id, name FROM budget_nodes ORDER BY rowid")
        return [BudgetNode(**dict(row)) for row in rows]


@router.post("/nodes", status_code=201)
def create_node(data: NewBudgetNode) -> BudgetNode:
    node = BudgetNode(id=uuid4().hex, parent_id=data.parent_id, name=data.name)
    with budget_db(write=True) as db:
        require_node(db, data.parent_id)
        db.execute(
            "INSERT INTO budget_nodes (id, parent_id, name) VALUES (?, ?, ?)",
            (node.id, node.parent_id, node.name),
        )
    return node


@router.post("/nodes/{node_id}/categories", status_code=201)
def create_category(node_id: str, data: NamedBudgetItem) -> CostCategory:
    category = CostCategory(id=uuid4().hex, node_id=node_id, name=data.name)
    with budget_db(write=True) as db:
        require_node(db, node_id)
        db.execute(
            "INSERT INTO budget_categories (id, node_id, name) VALUES (?, ?, ?)",
            (category.id, category.node_id, category.name),
        )
    return category


@router.patch("/nodes/{node_id}/categories/{category_id}")
def rename_category(node_id: str, category_id: str, data: NamedBudgetItem) -> CostCategory:
    with budget_db(write=True) as db:
        updated = db.execute(
            "UPDATE budget_categories SET name = ? WHERE id = ? AND node_id = ?",
            (data.name, category_id, node_id),
        )
        if updated.rowcount == 0:
            raise HTTPException(status_code=404, detail="Kostenart auf dieser Budgetebene nicht gefunden.")
    return CostCategory(id=category_id, node_id=node_id, name=data.name)


@router.get("/nodes/{node_id}/plans/{year}")
def get_plan(node_id: str, year: BudgetYear) -> AnnualPlan:
    with budget_db() as db:
        require_node(db, node_id)
        categories = available_categories(db, node_id)
        return annual_plan(node_id, year, categories, stored_costs(db, node_id, year))


@router.put("/nodes/{node_id}/plans/{year}")
def save_plan(node_id: str, year: BudgetYear, planned_cents: PlannedCosts) -> AnnualPlan:
    with budget_db(write=True) as db:
        require_node(db, node_id)
        categories = available_categories(db, node_id)
        amounts = planned_cents.root
        invalid_ids = amounts.keys() - {category.id for category in categories}
        if invalid_ids:
            raise HTTPException(status_code=422, detail={
                "message": "Kostenarten sind auf dieser Budgetebene nicht verfügbar.",
                "category_ids": sorted(invalid_ids),
            })

        plan = annual_plan(node_id, year, categories, amounts)
        db.execute("DELETE FROM budget_plans WHERE node_id = ? AND year = ?", (node_id, year))
        write_costs(db, node_id, year, {
            category_id: cents for category_id, cents in amounts.items() if cents
        })
    return plan


def budget_overview(db: sqlite3.Connection, year: int) -> BudgetOverview:
    limit = db.execute(
        "SELECT cents FROM project_budget_limits WHERE project_id = ? AND year = ?",
        (DEMO_PROJECT_ID, year),
    ).fetchone()
    totals = db.execute(
        """
        SELECT category.id, category.node_id, category.name, COALESCE(SUM(plan.cents), 0) AS planned_cents
        FROM budget_categories AS category
        LEFT JOIN budget_plans AS plan ON plan.category_id = category.id AND plan.year = ?
        GROUP BY category.id
        ORDER BY category.rowid
        """,
        (year,),
    )
    categories = [
        CategorySummary(
            category=CostCategory(id=row["id"], node_id=row["node_id"], name=row["name"]),
            planned_cents=row["planned_cents"],
        )
        for row in totals
    ]
    planned_total = sum(item.planned_cents for item in categories)
    return BudgetOverview(
        year=year,
        budget_limit_cents=limit["cents"] if limit is not None else None,
        planned_total_cents=planned_total,
        unallocated_cents=limit["cents"] - planned_total if limit is not None else None,
        categories=categories,
    )


@router.get("/{year}/overview")
def get_overview(year: BudgetYear) -> BudgetOverview:
    with budget_db() as db:
        return budget_overview(db, year)


@router.put("/{year}/limit")
def save_limit(year: BudgetYear, limit: BudgetLimit) -> BudgetOverview:
    with budget_db(write=True) as db:
        db.execute(
            """
            INSERT INTO project_budget_limits (project_id, year, cents) VALUES (?, ?, ?)
            ON CONFLICT (project_id, year) DO UPDATE SET cents = excluded.cents
            """,
            (DEMO_PROJECT_ID, year, limit.budget_limit_cents),
        )
        return budget_overview(db, year)


@router.get("/{year}")
def get_budget(year: BudgetYear) -> ProjectBudget:
    with budget_db() as db:
        costs = stored_costs(db, DEMO_PROJECT_ID, year)
    standard_amounts = {category_id: costs.get(category_id, 0) for category_id in STANDARD_CATEGORIES}
    return ProjectBudget(
        year=year,
        planned_cents=LegacyPlannedCosts(**standard_amounts),
        planned_total_cents=sum(standard_amounts.values()),
    )


@router.put("/{year}")
def save_budget(year: BudgetYear, planned_cents: LegacyPlannedCosts) -> ProjectBudget:
    costs = planned_cents.model_dump()
    with budget_db(write=True) as db:
        write_costs(db, DEMO_PROJECT_ID, year, costs)
    return ProjectBudget(year=year, planned_cents=planned_cents, planned_total_cents=sum(costs.values()))
