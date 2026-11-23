import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import Path as ApiPath
from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints

if __package__:
    from .budget_db import DEMO_PROJECT_ID, budget_db
else:
    from budget_db import DEMO_PROJECT_ID, budget_db

router = APIRouter(prefix=f"/api/projects/{DEMO_PROJECT_ID}/budgets", tags=["Project budgets"])

BudgetYear = Annotated[int, ApiPath(ge=2000, le=2100)]
Cents = Annotated[int, Field(strict=True, ge=0, le=999_999_999_999)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class PlannedCosts(RootModel[dict[str, Cents]]):
    """Annual planned amounts in cents by cost category ID."""


class CategoryName(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DisplayName


class CostCategory(BaseModel):
    id: str
    name: str


class AnnualPlan(BaseModel):
    project_id: Literal["demo-project"] = DEMO_PROJECT_ID
    year: int
    categories: list[CostCategory]
    planned_cents: PlannedCosts
    planned_total_cents: int


def read_plan(db: sqlite3.Connection, year: int) -> AnnualPlan:
    rows = db.execute("""
        SELECT category.id, category.name, COALESCE(plan.cents, 0)
        FROM planning_categories AS category
        LEFT JOIN annual_plans AS plan ON plan.category_id = category.id AND plan.year = ?
        ORDER BY category.rowid
    """, (year,)).fetchall()
    amounts = {category_id: cents for category_id, _, cents in rows}
    return AnnualPlan(
        year=year,
        categories=[CostCategory(id=category_id, name=name) for category_id, name, _ in rows],
        planned_cents=PlannedCosts(amounts),
        planned_total_cents=sum(amounts.values()),
    )


@router.post("/categories", status_code=201)
def create_category(data: CategoryName) -> CostCategory:
    category = CostCategory(id=uuid4().hex, name=data.name)
    with budget_db(write=True) as db:
        db.execute("INSERT INTO planning_categories (id, name) VALUES (?, ?)", (category.id, category.name))
    return category


@router.patch("/categories/{category_id}")
def rename_category(category_id: str, data: CategoryName) -> CostCategory:
    with budget_db(write=True) as db:
        updated = db.execute("UPDATE planning_categories SET name = ? WHERE id = ?", (data.name, category_id))
        if updated.rowcount == 0:
            raise HTTPException(status_code=404, detail="Kostenart nicht gefunden.")
    return CostCategory(id=category_id, name=data.name)


@router.get("/{year}")
def get_plan(year: BudgetYear) -> AnnualPlan:
    with budget_db() as db:
        return read_plan(db, year)


@router.put("/{year}")
def save_plan(year: BudgetYear, planned_cents: PlannedCosts) -> AnnualPlan:
    amounts = planned_cents.root
    with budget_db(write=True) as db:
        category_ids = {category_id for category_id, in db.execute("SELECT id FROM planning_categories")}
        unknown = amounts.keys() - category_ids
        if unknown:
            raise HTTPException(status_code=422, detail={
                "message": "Unbekannte Kostenarten.",
                "category_ids": sorted(unknown),
            })

        db.execute("DELETE FROM annual_plans WHERE year = ?", (year,))
        db.executemany(
            "INSERT INTO annual_plans (year, category_id, cents) VALUES (?, ?, ?)",
            [(year, category_id, cents) for category_id, cents in amounts.items() if cents],
        )
        return read_plan(db, year)
