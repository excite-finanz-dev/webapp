from collections.abc import Callable, Sequence
from enum import Enum
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

if __package__:
    from .budget_db import DEMO_PROJECT_ID
else:
    from budget_db import DEMO_PROJECT_ID


class Role(str, Enum):
    ADMIN = "admin"  # Finanzabteilung: configures the application
    BOARD_OF_DIRECTORS = "board_of_directors"  # Vorstand: overview of the whole budget
    MEASURE_LEADS = "measure_leads"
    ACTION_LINE_Teams = "action_line_teams"
    PROJECT_EMPLOYEES = "project_employees"


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"  # add and edit budget data
    CONFIGURE = "configure"  # change the structure, e.g. cost categories


# What each role may do at all. Where it may do it is decided by User.has_permission.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({Permission.READ, Permission.WRITE, Permission.CONFIGURE}),
    Role.BOARD_OF_DIRECTORS: frozenset({Permission.READ}),
    Role.MEASURE_LEADS: frozenset({Permission.READ, Permission.WRITE}),
    Role.ACTION_LINE_TEAMS: frozenset({Permission.READ, Permission.WRITE}),
    Role.PROJECT_EMPLOYEES: frozenset({Permission.READ, Permission.WRITE}),
}

# These roles see the whole hierarchy. All other roles are tied to one node.
GLOBAL_ROLES = frozenset({Role.ADMIN, Role.BOARD_OF_DIRECTORS})


class User(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    vorname: str
    nachname: str
    uni: str
    role: Role
    # ID of the measure, action line or project this user belongs to.
    # Required for every role that is not global.
    node_id: str | None = None

    @model_validator(mode="after")
    def check_node_id(self) -> "User":
        if self.role not in GLOBAL_ROLES and not self.node_id:
            raise ValueError(f"Role '{self.role.value}' needs a node_id.")
        return self
