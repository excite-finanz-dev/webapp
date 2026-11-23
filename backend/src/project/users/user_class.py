from enum import Enum
from pydantic import BaseModel, ConfigDict


class Role(str, Enum):
    ADMIN = "admin"
    BOARD_OF_DIRECTORS = "board_of_directors"
    MEASURE_LEADS = "measure_leads"
    ACTION_LINE_Teams = "action_line_teams"
    PROJECT_EMPLOYEES = "project_employees"


class User(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    vorname: str
    nachname: str
    uni: str
    role: Role

    #def methode_name():<