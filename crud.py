"""Database-access helpers for users and contacts (no HTTP layer here).

Every function takes a SQLAlchemy ``Session`` and returns ORM objects (or
``None``); turning those into HTTP responses is the job of ``main.py``.
"""
from datetime import date

from sqlalchemy.orm import Session

import models
import schemas


def create_user(db: Session, user: schemas.UserCreate, hashed_password: str) -> models.User:
    """Insert a new, unconfirmed ``"user"``-role account."""
    db_user = models.User(
        username=user.username,
        email=str(user.email),
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_email(db: Session, email: str) -> models.User | None:
    """Look up a user by email, or return ``None``."""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    """Look up a user by username, or return ``None``."""
    return db.query(models.User).filter(models.User.username == username).first()


def confirm_user_email(db: Session, user: models.User) -> models.User:
    """Mark a user's email address as confirmed."""
    user.confirmed = True
    db.commit()
    db.refresh(user)
    return user


def update_user_avatar(db: Session, user: models.User, avatar_url: str) -> models.User:
    """Persist a new avatar URL for a user."""
    user.avatar = avatar_url
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user: models.User, hashed_password: str) -> models.User:
    """Replace a user's stored password hash."""
    user.hashed_password = hashed_password
    db.commit()
    db.refresh(user)
    return user


def update_user_role(db: Session, user: models.User, role: str) -> models.User:
    """Change a user's role (e.g. ``"user"`` -> ``"admin"``)."""
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def create_contact(db: Session, contact: schemas.ContactCreate, user_id: int) -> models.Contact:
    """Insert a new contact owned by ``user_id``."""
    db_contact = models.Contact(**contact.model_dump(), user_id=user_id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def get_contact(db: Session, contact_id: int, user_id: int) -> models.Contact | None:
    """Fetch one contact, scoped to its owner so other users get ``None``."""
    return (
        db.query(models.Contact)
        .filter(models.Contact.id == contact_id, models.Contact.user_id == user_id)
        .first()
    )


def get_contacts(db: Session, user_id: int, skip: int = 0, limit: int = 10) -> list[models.Contact]:
    """Return a paginated slice of a user's contacts."""
    return (
        db.query(models.Contact)
        .filter(models.Contact.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_contact(
    db: Session, contact_id: int, user_id: int, contact: schemas.ContactUpdate
) -> models.Contact | None:
    """Apply only the fields provided in ``contact``; ``None`` if not found."""
    db_contact = get_contact(db, contact_id, user_id)
    if db_contact is None:
        return None
    for field, value in contact.model_dump(exclude_unset=True).items():
        setattr(db_contact, field, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def delete_contact(db: Session, contact_id: int, user_id: int) -> models.Contact | None:
    """Delete and return a contact, or ``None`` if it doesn't exist / isn't owned."""
    db_contact = get_contact(db, contact_id, user_id)
    if db_contact is None:
        return None
    db.delete(db_contact)
    db.commit()
    return db_contact


def search_contacts(
    db: Session,
    user_id: int,
    first_name: str | None,
    last_name: str | None,
    email: str | None,
) -> list[models.Contact]:
    """Case-insensitive partial-match search across name/email fields."""
    query = db.query(models.Contact).filter(models.Contact.user_id == user_id)
    if first_name:
        query = query.filter(models.Contact.first_name.ilike(f"%{first_name}%"))
    if last_name:
        query = query.filter(models.Contact.last_name.ilike(f"%{last_name}%"))
    if email:
        query = query.filter(models.Contact.email.ilike(f"%{email}%"))
    return query.all()


def get_upcoming_birthdays(db: Session, user_id: int) -> list[models.Contact]:
    """Return contacts whose birthday falls within the next 7 days.

    Handles the year-end wraparound (e.g. Dec 28 -> Jan 3) and never raises
    for a Feb 29 birthday checked in a non-leap year.
    """

    def _next_occurrence(birthday: date, today: date) -> date:
        for year in (today.year, today.year + 1):
            try:
                occurrence = birthday.replace(year=year)
            except ValueError:
                # Feb 29 in a non-leap year: treat the birthday as Mar 1.
                occurrence = date(year, 3, 1)
            if occurrence >= today:
                return occurrence
        # Unreachable in practice, but keeps the function total.
        return birthday.replace(year=today.year + 1)

    today = date.today()
    contacts = db.query(models.Contact).filter(models.Contact.user_id == user_id).all()
    return [
        contact
        for contact in contacts
        if 0 <= (_next_occurrence(contact.birthday, today) - today).days <= 7
    ]