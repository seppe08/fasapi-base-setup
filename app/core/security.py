from pwdlib import PasswordHash

__password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return __password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return __password_hash.verify(password, hashed)
