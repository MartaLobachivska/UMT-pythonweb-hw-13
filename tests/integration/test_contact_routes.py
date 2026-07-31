"""Integration tests for the contacts routes (create/read/update/delete/search)."""
from datetime import date, timedelta


def _contact_json(**overrides):
    data = dict(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+380001112233",
        birthday="1990-05-20",
        additional_data=None,
    )
    data.update(overrides)
    return data


class TestContactsRequireAuth:
    def test_list_contacts_without_token_returns_401(self, client):
        assert client.get("/contacts/").status_code == 401

    def test_create_contact_without_token_returns_401(self, client):
        response = client.post("/contacts/", json=_contact_json())
        assert response.status_code == 401


class TestContactCrud:
    def test_create_contact(self, client, make_user, auth_headers):
        user = make_user()
        response = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(user)
        )
        assert response.status_code == 201
        body = response.json()
        assert body["first_name"] == "John"
        assert body["user_id"] == user.id

    def test_create_contact_invalid_email_returns_422(self, client, make_user, auth_headers):
        user = make_user()
        response = client.post(
            "/contacts/",
            json=_contact_json(email="not-an-email"),
            headers=auth_headers(user),
        )
        assert response.status_code == 422

    def test_list_contacts(self, client, make_user, auth_headers):
        user = make_user()
        client.post("/contacts/", json=_contact_json(), headers=auth_headers(user))
        response = client.get("/contacts/", headers=auth_headers(user))
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_single_contact(self, client, make_user, auth_headers):
        user = make_user()
        created = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(user)
        ).json()
        response = client.get(f"/contacts/{created['id']}", headers=auth_headers(user))
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_missing_contact_returns_404(self, client, make_user, auth_headers):
        user = make_user()
        response = client.get("/contacts/9999", headers=auth_headers(user))
        assert response.status_code == 404

    def test_update_contact(self, client, make_user, auth_headers):
        user = make_user()
        created = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(user)
        ).json()
        response = client.put(
            f"/contacts/{created['id']}",
            json={"first_name": "Jane"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "Jane"

    def test_delete_contact(self, client, make_user, auth_headers):
        user = make_user()
        created = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(user)
        ).json()
        response = client.delete(f"/contacts/{created['id']}", headers=auth_headers(user))
        assert response.status_code == 200
        assert client.get(f"/contacts/{created['id']}", headers=auth_headers(user)).status_code == 404


class TestContactIsolationBetweenUsers:
    def test_user_cannot_read_another_users_contact(self, client, make_user, auth_headers):
        owner = make_user(username="owner", email="owner@example.com")
        intruder = make_user(username="intruder", email="intruder@example.com")
        created = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(owner)
        ).json()
        response = client.get(f"/contacts/{created['id']}", headers=auth_headers(intruder))
        assert response.status_code == 404

    def test_user_cannot_delete_another_users_contact(self, client, make_user, auth_headers):
        owner = make_user(username="owner", email="owner@example.com")
        intruder = make_user(username="intruder", email="intruder@example.com")
        created = client.post(
            "/contacts/", json=_contact_json(), headers=auth_headers(owner)
        ).json()
        response = client.delete(f"/contacts/{created['id']}", headers=auth_headers(intruder))
        assert response.status_code == 404


class TestSearchAndBirthdays:
    def test_search_by_first_name(self, client, make_user, auth_headers):
        user = make_user()
        client.post(
            "/contacts/", json=_contact_json(first_name="Alice"), headers=auth_headers(user)
        )
        client.post(
            "/contacts/",
            json=_contact_json(first_name="Bob", email="bob@example.com"),
            headers=auth_headers(user),
        )
        response = client.get("/search/?first_name=ali", headers=auth_headers(user))
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["first_name"] == "Alice"

    def test_upcoming_birthdays(self, client, make_user, auth_headers):
        user = make_user()
        soon = (date.today() + timedelta(days=2)).replace(year=1990)
        client.post(
            "/contacts/",
            json=_contact_json(birthday=soon.isoformat(), email="soon@example.com"),
            headers=auth_headers(user),
        )
        response = client.get("/birthdays/", headers=auth_headers(user))
        assert response.status_code == 200
        assert len(response.json()) == 1