from .users_enum import Role

class User:
    def __init__(self, vorname, nachname, uni, role):
        self.vorname = vorname
        self.nachname = nachname
        self.uni = uni
        self.role = role

    def __setattr__(self, role, value):
        if role == "role" and not isinstance(value, Role):
            raise TypeError(f"{role} must be Role, got {type(value).__role__}")
        super().__setattr__(role, value)

    #def methode_name():<