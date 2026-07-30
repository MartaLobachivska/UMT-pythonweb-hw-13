from datetime import date, timedelta

from sqlalchemy.orm import Session

import models
import schemas


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def create_user(db: Session, user: schemas.UserCreate, hashed_password: str) -> models.User:
    db_user = models.User(
        username=user.username,
        email=str(user.email),
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def confirm_user_email(db: Session, user: models.User) -> None:
    user.confirmed = True
    db.commit()


def update_user_avatar(db: Session, user: models.User, avatar_url: str) -> models.User:
    user.avatar = avatar_url
    db.commit()
    db.refresh(user)
    return user


def get_contacts(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Contact)
        .filter(models.Contact.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_contact(db: Session, contact_id: int, user_id: int) -> models.Contact | None:
    return (
        db.query(models.Contact)
        .filter(models.Contact.id == contact_id, models.Contact.user_id == user_id)
        .first()
    )


def create_contact(db: Session, contact: schemas.ContactCreate, user_id: int) -> models.Contact:
    db_contact = models.Contact(**contact.model_dump(), user_id=user_id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def update_contact(
    db: Session, contact_id: int, user_id: int, contact: schemas.ContactUpdate
) -> models.Contact | None:
    db_contact = get_contact(db, contact_id, user_id)
    if db_contact is None:
        return None
    for key, value in contact.model_dump(exclude_unset=True).items():
        setattr(db_contact, key, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def delete_contact(db: Session, contact_id: int, user_id: int) -> models.Contact | None:
    db_contact = get_contact(db, contact_id, user_id)
    if db_contact is None:
        return None
    db.delete(db_contact)
    db.commit()
    return db_contact


def search_contacts(
    db: Session, user_id: int, first_name: str | None, last_name: str | None, email: str | None
):
    query = db.query(models.Contact).filter(models.Contact.user_id == user_id)
    if first_name:
        query = query.filter(models.Contact.first_name.ilike(f"%{first_name}%"))
    if last_name:
        query = query.filter(models.Contact.last_name.ilike(f"%{last_name}%"))
    if email:
        query = query.filter(models.Contact.email.ilike(f"%{email}%"))
    return query.all()


def get_upcoming_birthdays(db: Session, user_id: int):
    today = date.today()
    end_date = today + timedelta(days=7)
    result = []
    for contact in db.query(models.Contact).filter(models.Contact.user_id == user_id).all():
        try:
            birthday_this_year = contact.birthday.replace(year=today.year)
        except ValueError:  # 29 February in a non-leap year
            birthday_this_year = contact.birthday.replace(year=today.year, day=28)
        if birthday_this_year < today:
            birthday_this_year = birthday_this_year.replace(year=today.year + 1)
        if today <= birthday_this_year <= end_date:
            result.append(contact)
    return result
