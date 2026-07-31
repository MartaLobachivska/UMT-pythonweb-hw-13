"""Unit tests for crud.py (no HTTP layer, direct DB session calls)."""
from datetime import date, timedelta

import pytest

import crud
import schemas


def _make_user(db_session, username="anna", email="anna@example.com"):
    return crud.create_user(
        db_session,
        schemas.UserCreate(username=username, email=email, password="strongpassword1"),
        hashed_password="hashed-value",
    )


class TestUserCrud:
    def test_create_user_sets_defaults(self, db_session):
        user = _make_user(db_session)
        assert user.id is not None
        assert user.confirmed is False
        assert user.role == "user"
        assert user.hashed_password == "hashed-value"

    def test_get_user_by_email_found_and_missing(self, db_session):
        _make_user(db_session)
        assert crud.get_user_by_email(db_session, "anna@example.com") is not None
        assert crud.get_user_by_email(db_session, "nobody@example.com") is None

    def test_get_user_by_username_found_and_missing(self, db_session):
        _make_user(db_session)
        assert crud.get_user_by_username(db_session, "anna") is not None
        assert crud.get_user_by_username(db_session, "ghost") is None

    def test_confirm_user_email(self, db_session):
        user = _make_user(db_session)
        assert user.confirmed is False
        crud.confirm_user_email(db_session, user)
        assert user.confirmed is True

    def test_update_user_avatar(self, db_session):
        user = _make_user(db_session)
        updated = crud.update_user_avatar(db_session, user, "https://example.com/a.png")
        assert updated.avatar == "https://example.com/a.png"

    def test_update_user_password(self, db_session):
        user = _make_user(db_session)
        updated = crud.update_user_password(db_session, user, "new-hash")
        assert updated.hashed_password == "new-hash"

    def test_update_user_role(self, db_session):
        user = _make_user(db_session)
        updated = crud.update_user_role(db_session, user, "admin")
        assert updated.role == "admin"


def _contact_payload(**overrides):
    data = dict(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+380001112233",
        birthday=date(1990, 5, 20),
        additional_data=None,
    )
    data.update(overrides)
    return schemas.ContactCreate(**data)


class TestContactCrud:
    def test_create_and_get_contact(self, db_session):
        user = _make_user(db_session)
        contact = crud.create_contact(db_session, _contact_payload(), user.id)
        fetched = crud.get_contact(db_session, contact.id, user.id)
        assert fetched is not None
        assert fetched.first_name == "John"

    def test_get_contact_wrong_owner_returns_none(self, db_session):
        owner = _make_user(db_session, "owner", "owner@example.com")
        other = _make_user(db_session, "other", "other@example.com")
        contact = crud.create_contact(db_session, _contact_payload(), owner.id)
        assert crud.get_contact(db_session, contact.id, other.id) is None

    def test_get_contacts_pagination(self, db_session):
        user = _make_user(db_session)
        for i in range(5):
            crud.create_contact(
                db_session, _contact_payload(email=f"c{i}@example.com"), user.id
            )
        page = crud.get_contacts(db_session, user.id, skip=0, limit=2)
        assert len(page) == 2

    def test_update_contact(self, db_session):
        user = _make_user(db_session)
        contact = crud.create_contact(db_session, _contact_payload(), user.id)
        updated = crud.update_contact(
            db_session, contact.id, user.id, schemas.ContactUpdate(first_name="Jane")
        )
        assert updated.first_name == "Jane"
        assert updated.last_name == "Doe"  # untouched fields survive

    def test_update_contact_not_found(self, db_session):
        user = _make_user(db_session)
        result = crud.update_contact(
            db_session, 9999, user.id, schemas.ContactUpdate(first_name="Jane")
        )
        assert result is None

    def test_delete_contact(self, db_session):
        user = _make_user(db_session)
        contact = crud.create_contact(db_session, _contact_payload(), user.id)
        deleted = crud.delete_contact(db_session, contact.id, user.id)
        assert deleted.id == contact.id
        assert crud.get_contact(db_session, contact.id, user.id) is None

    def test_delete_contact_not_found(self, db_session):
        user = _make_user(db_session)
        assert crud.delete_contact(db_session, 9999, user.id) is None

    def test_search_contacts_by_first_name(self, db_session):
        user = _make_user(db_session)
        crud.create_contact(db_session, _contact_payload(first_name="Alice"), user.id)
        crud.create_contact(
            db_session, _contact_payload(first_name="Bob", email="bob@example.com"), user.id
        )
        results = crud.search_contacts(db_session, user.id, "ali", None, None)
        assert len(results) == 1
        assert results[0].first_name == "Alice"

    def test_upcoming_birthdays_within_next_7_days(self, db_session):
        user = _make_user(db_session)
        soon = date.today() + timedelta(days=3)
        far = date.today() + timedelta(days=100)
        crud.create_contact(
            db_session,
            _contact_payload(birthday=soon.replace(year=1990), email="soon@example.com"),
            user.id,
        )
        crud.create_contact(
            db_session,
            _contact_payload(birthday=far.replace(year=1990), email="far@example.com"),
            user.id,
        )
        upcoming = crud.get_upcoming_birthdays(db_session, user.id)
        emails = {c.email for c in upcoming}
        assert "soon@example.com" in emails
        assert "far@example.com" not in emails

    def test_upcoming_birthdays_handles_feb_29(self, db_session):
        user = _make_user(db_session)
        crud.create_contact(
            db_session,
            _contact_payload(birthday=date(1996, 2, 29), email="leap@example.com"),
            user.id,
        )
        # Should not raise even in a non-leap year.
        result = crud.get_upcoming_birthdays(db_session, user.id)
        assert isinstance(result, list)