from .users_enum import Role
from pydantic import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    vorname: str
    nachname: str
    uni: str
    role: Role

    #def methode_name():<