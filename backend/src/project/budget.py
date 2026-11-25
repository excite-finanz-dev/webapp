from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from uuid import uuid4


STANDARD_CATEGORIES = MappingProxyType({
    "personnel": "Personalkosten",
    "material": "Materialkosten",
    "other": "Sonstiges",
})


class Budget:
    """A budget at any level, with cost categories and plans at the leaves."""

    def __init__(
        self,
        name: str,
        *,
        budget_id: str | None = None,
        categories: Mapping[str, str] = STANDARD_CATEGORIES,
    ) -> None:
        self.name = name
        self._id = uuid4().hex if budget_id is None else budget_id
        self._parent: Budget | None = None
        self._children: list[Budget] = []
        self._categories = dict(categories)
        self._plans: dict[int, dict[str, int]] = {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def parent(self) -> Budget | None:
        return self._parent

    @property
    def children(self) -> tuple[Budget, ...]:
        return tuple(self._children)

    @property
    def is_leaf(self) -> bool:
        return not self._children

    @property
    def node_path(self) -> tuple[str, ...]:
        """Return budget IDs from the root to this budget."""
        return tuple(reversed([budget.id for budget in self._ancestors()]))

    @property
    def categories(self) -> dict[str, str]:
        return self._categories.copy() if self.is_leaf else {}

    def add_child(self, child: Budget) -> None:
        child.move_to(self)

    def move_to(self, parent: Budget | None) -> None:
        """Move the entire subtree, or detach it when parent is None."""
        if parent is self._parent:
            return
        if parent is not None:
            ancestors = list(parent._ancestors())
            if self in ancestors:
                raise ValueError("A budget cannot be moved under itself or one of its descendants.")
            if parent._plans or parent._categories != STANDARD_CATEGORIES:
                raise ValueError("A budget with planned costs or custom categories cannot have child budgets.")

            root = ancestors[-1]
            if root not in self._ancestors():
                moving_ids = {budget.id for budget in self._subtree()}
                if any(budget.id in moving_ids for budget in root._subtree()):
                    raise ValueError("Budget IDs must be unique within a hierarchy.")

        if self._parent is not None:
            self._parent._children.remove(self)
        if parent is not None:
            parent._children.append(self)
        self._parent = parent

    def add_category(self, name: str) -> str:
        self._require_leaf()
        category_id = uuid4().hex
        self._categories[category_id] = self._category_name(name)
        return category_id

    def rename_category(self, category_id: str, name: str) -> None:
        self._require_leaf()
        if category_id not in self._categories:
            raise KeyError(category_id)
        self._categories[category_id] = self._category_name(name)

    def set_plan(self, year: int, amounts: Mapping[str, int]) -> None:
        """Replace a leaf's annual plan. Omitted categories have zero costs."""
        self._require_leaf()
        unknown = amounts.keys() - self._categories.keys()
        if unknown:
            raise ValueError(f"Unknown cost categories: {', '.join(sorted(unknown))}")
        if any(type(cents) is not int or cents < 0 for cents in amounts.values()):
            raise ValueError("Planned costs must be non-negative integer cents.")

        planned_costs = {category_id: cents for category_id, cents in amounts.items() if cents}
        if planned_costs:
            self._plans[year] = planned_costs
        else:
            self._plans.pop(year, None)

    def planned_costs(self, year: int) -> dict[str, int]:
        self._require_leaf()
        amounts = self._plans.get(year, {})
        return {category_id: amounts.get(category_id, 0) for category_id in self._categories}

    def planned_total_cents(self, year: int) -> int:
        """Sum the annual costs across the leaves of this budget's subtree."""
        return sum(sum(budget._plans.get(year, {}).values()) for budget in self._subtree())

    def _ancestors(self) -> Iterator[Budget]:
        budget: Budget | None = self
        while budget is not None:
            yield budget
            budget = budget._parent

    def _subtree(self) -> Iterator[Budget]:
        pending = [self]
        while pending:
            budget = pending.pop()
            yield budget
            pending.extend(budget._children)

    def _require_leaf(self) -> None:
        if not self.is_leaf:
            raise ValueError("Only budgets without children have cost categories and annual plans.")

    @staticmethod
    def _category_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("A cost category name is required.")
        return name
