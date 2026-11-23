from enum import Enum
from pydantic import BaseModel, ConfigDict, model_validator

if __package__:
    from .budget_db import DEMO_PROJECT_ID
else:
    from budget_db import DEMO_PROJECT_ID


class Role(str, Enum):
    ADMIN = "admin"
    BOARD_OF_DIRECTORS = "board_of_directors"
    MEASURE_LEADS = "measure_leads"
    ACTION_LINE_Teams = "action_line_teams"
    PROJECT_EMPLOYEES = "project_employees"


class Permission(str, Enum):
    READ = "read"
    WRITE = "write" 
    CONFIGURE = "configure"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({Permission.READ, Permission.WRITE, Permission.CONFIGURE}),
    Role.BOARD_OF_DIRECTORS: frozenset({Permission.READ}),
    Role.MEASURE_LEADS: frozenset({Permission.READ, Permission.WRITE}),
    Role.ACTION_LINE_TEAMS: frozenset({Permission.READ, Permission.WRITE}),
    Role.PROJECT_EMPLOYEES: frozenset({Permission.READ, Permission.WRITE}),
}

GLOBAL_ROLES = frozenset({Role.ADMIN, Role.BOARD_OF_DIRECTORS})


class User(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    vorname: str
    nachname: str
    uni: str
    role: Role
    node_id: str | None = None

    @model_validator(mode="after")
    def check_node_id(self) -> "User":
        if self.role not in GLOBAL_ROLES and not self.node_id:
            raise ValueError(f"Role '{self.role.value}' needs a node_id.")
        return self
