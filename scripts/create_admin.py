"""
Birinchi administratorni yaratish (yoki mavjud adminning parolini tiklash).

    docker compose run --rm api python -m scripts.create_admin --login admin --full-name "Ali Valiyev"

Parol interaktiv so'raladi. Avtomatlashtirish uchun ADMIN_PASSWORD muhit
o'zgaruvchisi ishlatilishi mumkin. Parol hech qachon logga yozilmaydi.
"""

import argparse
import getpass
import os
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from database.config import SessionLocal
from database.hash import Hash
from models import User, UserRole
from schemas.common import FullName, Login, Password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first admin user")
    parser.add_argument("--login", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--reset", action="store_true", help="login mavjud bo'lsa, parolini tiklash")
    args = parser.parse_args()

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Parol: ")
    if not os.environ.get("ADMIN_PASSWORD") and getpass.getpass("Parolni takrorlang: ") != password:
        print("Parollar mos kelmadi.", file=sys.stderr)
        return 1

    try:
        login = TypeAdapter(Login).validate_python(args.login)
        full_name = TypeAdapter(FullName).validate_python(args.full_name)
        TypeAdapter(Password).validate_python(password)
    except ValidationError as e:
        print(f"Notoʻgʻri qiymat: {e.errors()[0]['msg']}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.login == login)).first()
        if user and not args.reset:
            print(f"'{login}' allaqachon bor. Parolni tiklash uchun --reset qoʻshing.", file=sys.stderr)
            return 1
        if user:
            user.password_hash = Hash.bcrypt(password)
            user.role = UserRole.ADMIN
            user.is_active = True
            user.must_change_password = False
            user.failed_login_count = 0
            user.locked_until = None
            user.token_version += 1
            action = "yangilandi"
        else:
            db.add(
                User(
                    full_name=full_name,
                    login=login,
                    role=UserRole.ADMIN,
                    password_hash=Hash.bcrypt(password),
                    must_change_password=False,
                )
            )
            action = "yaratildi"
        db.commit()
    print(f"Administrator '{login}' {action}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
