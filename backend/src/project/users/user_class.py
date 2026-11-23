from .users_enum import Role

class User:
    def __init__(self, vorname, nachname, uni, role):
        self.vorname = vorname
        self.nachname = nachname
        self.uni = uni
        self.role = role

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        if not isinstance(value, Role):
            raise TypeError(
                f"role must be Role, got {type(value).__name__}"
            )
        self._role = value

    #def methode_name():<