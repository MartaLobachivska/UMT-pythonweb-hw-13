from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

import models
import schemas
import crud
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Contacts API",
    description="API для управління контактами (FastAPI + PostgreSQL + SQLAlchemy)",
    version="1.0.0"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/", summary="Перевірка роботи API")
def root():
    return {"message": "Contacts API is running 🚀"}


@app.post(
    "/contacts/",
    response_model=schemas.ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Створити новий контакт"
)
def create_contact(contact: schemas.ContactCreate, db: Session = Depends(get_db)):
    existing = crud.get_contact_by_email(db, contact.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    return crud.create_contact(db, contact)


@app.get(
    "/contacts/",
    response_model=List[schemas.ContactResponse],
    summary="Отримати список контактів"
)
def read_contacts(
    skip: int = Query(0, ge=0, description="Скільки записів пропустити"),
    limit: int = Query(10, ge=1, le=100, description="Кількість записів"),
    db: Session = Depends(get_db)
):
    return crud.get_contacts(db, skip, limit)


@app.get(
    "/contacts/{contact_id}",
    response_model=schemas.ContactResponse,
    summary="Отримати контакт за ID"
)
def read_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = crud.get_contact(db, contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return contact


@app.put(
    "/contacts/{contact_id}",
    response_model=schemas.ContactResponse,
    summary="Оновити контакт"
)
def update_contact(
    contact_id: int,
    contact: schemas.ContactUpdate,
    db: Session = Depends(get_db)
):
    updated = crud.update_contact(db, contact_id, contact)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return updated


@app.delete(
    "/contacts/{contact_id}",
    response_model=schemas.ContactResponse,
    summary="Видалити контакт"
)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_contact(db, contact_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return deleted


@app.get(
    "/search/",
    response_model=List[schemas.ContactResponse],
    summary="Пошук контактів"
)
def search_contacts(
    first_name: Optional[str] = Query(None, description="Пошук за ім'ям"),
    last_name: Optional[str] = Query(None, description="Пошук за прізвищем"),
    email: Optional[str] = Query(None, description="Пошук за email"),
    db: Session = Depends(get_db)
):
    results = crud.search_contacts(db, first_name, last_name, email)

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contacts found"
        )

    return results


@app.get(
    "/birthdays/",
    response_model=List[schemas.ContactResponse],
    summary="Контакти з днями народження на найближчі 7 днів"
)
def upcoming_birthdays(db: Session = Depends(get_db)):
    return crud.get_upcoming_birthdays(db)