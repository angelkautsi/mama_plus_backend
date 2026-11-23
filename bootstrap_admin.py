from getpass import getpass

from sqlalchemy.exc import IntegrityError

from backend.security.password import hash_password
from database.database import SessionLocal
from database.models import User


def main() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "admin").first():
            raise SystemExit("An administrator already exists; refusing to create another.")

        username = input("Administrator username: ").strip()
        email = input("Administrator email: ").strip()
        password = getpass("Administrator password (minimum 8 characters): ")
        if len(username) < 3 or len(email) < 5 or len(password) < 8:
            raise SystemExit("Username, email, or password does not meet minimum length.")
        if db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first():
            raise SystemExit("That username or email is already registered.")

        db.add(User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        ))
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise SystemExit("Could not create the administrator because the account conflicts.") from error
        print("Administrator account created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
