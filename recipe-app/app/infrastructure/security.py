from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.domain.contracts import IPasswordHasher


class Argon2PasswordHasher(IPasswordHasher):
    def __init__(self):
        self.password_hash = PasswordHash.recommended()
        self.dummy_hash = self.password_hash.hash("dummy-password-for-timing-only")

    def hash(self, password: str) -> str:
        return self.password_hash.hash(password)

    def verify(self, password: str, password_hash: str | None) -> bool:
        try:
            valid = self.password_hash.verify(password, password_hash or self.dummy_hash)
        except UnknownHashError:
            return False
        return password_hash is not None and valid
