"""Integration tests for /auth/* and /admin/* routes, through real HTTP calls."""
import security


def _signup(client, username="anna", email="anna@example.com", password="strongpassword1"):
    return client.post(
        "/auth/signup",
        json={"username": username, "email": email, "password": password},
    )


class TestSignup:
    def test_signup_returns_201(self, client):
        response = _signup(client)
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "anna@example.com"
        assert body["confirmed"] is False
        assert "hashed_password" not in body

    def test_signup_duplicate_email_returns_409(self, client):
        _signup(client, username="anna", email="dup@example.com")
        response = _signup(client, username="different", email="dup@example.com")
        assert response.status_code == 409

    def test_signup_duplicate_username_returns_409(self, client):
        _signup(client, username="anna", email="a1@example.com")
        response = _signup(client, username="anna", email="a2@example.com")
        assert response.status_code == 409


class TestLogin:
    def test_login_with_correct_credentials_returns_token_pair(self, client, make_user):
        make_user(username="anna", email="anna@example.com", password="strongpassword1")
        response = client.post(
            "/auth/login", data={"username": "anna", "password": "strongpassword1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_accepts_email_as_username_field(self, client, make_user):
        make_user(username="anna", email="anna@example.com", password="strongpassword1")
        response = client.post(
            "/auth/login", data={"username": "anna@example.com", "password": "strongpassword1"}
        )
        assert response.status_code == 200

    def test_login_wrong_password_returns_401(self, client, make_user):
        make_user(username="anna", email="anna@example.com", password="strongpassword1")
        response = client.post(
            "/auth/login", data={"username": "anna", "password": "wrongpassword"}
        )
        assert response.status_code == 401

    def test_login_unknown_user_returns_401(self, client):
        response = client.post(
            "/auth/login", data={"username": "ghost", "password": "whatever123"}
        )
        assert response.status_code == 401


class TestRefresh:
    def test_refresh_returns_new_token_pair(self, client, make_user):
        user = make_user()
        refresh_token = security.create_refresh_token({"sub": user.email, "user_id": user.id})
        response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_refresh_rejects_access_token(self, client, make_user):
        user = make_user()
        access_token = security.create_access_token({"sub": user.email, "user_id": user.id})
        response = client.post("/auth/refresh", json={"refresh_token": access_token})
        assert response.status_code == 401

    def test_refresh_rejects_garbage_token(self, client):
        response = client.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})
        assert response.status_code == 401


class TestEmailConfirmation:
    def test_confirm_email_with_valid_token(self, client, make_user):
        user = make_user(confirmed=False)
        token = security.create_email_token({"sub": user.email})
        response = client.get(f"/auth/confirmed_email?token={token}")
        assert response.status_code == 200
        assert response.json()["message"] == "Email confirmed"

    def test_confirm_email_already_confirmed(self, client, make_user):
        user = make_user(confirmed=True)
        token = security.create_email_token({"sub": user.email})
        response = client.get(f"/auth/confirmed_email?token={token}")
        assert response.json()["message"] == "Email already confirmed"

    def test_confirm_email_invalid_token(self, client):
        response = client.get("/auth/confirmed_email?token=garbage")
        assert response.status_code == 400

    def test_request_email_does_not_leak_account_existence(self, client):
        response = client.post("/auth/request_email", params={"email": "ghost@example.com"})
        assert response.status_code == 200
        assert "If this email exists" in response.json()["message"]


class TestPasswordReset:
    def test_request_password_reset_always_returns_202(self, client, make_user):
        make_user(email="anna@example.com")
        response = client.post(
            "/auth/request-password-reset", json={"email": "anna@example.com"}
        )
        assert response.status_code == 202

    def test_request_password_reset_unknown_email_still_202(self, client):
        response = client.post(
            "/auth/request-password-reset", json={"email": "ghost@example.com"}
        )
        assert response.status_code == 202

    def test_reset_password_with_valid_token_updates_password(self, client, make_user):
        user = make_user(password="oldpassword1")
        token = security.create_password_reset_token({"sub": user.email})
        response = client.post(
            "/auth/reset-password", json={"token": token, "password": "newpassword1"}
        )
        assert response.status_code == 200

        login = client.post(
            "/auth/login", data={"username": user.username, "password": "newpassword1"}
        )
        assert login.status_code == 200

    def test_reset_password_rejects_invalid_token(self, client):
        response = client.post(
            "/auth/reset-password", json={"token": "garbage", "password": "newpassword1"}
        )
        assert response.status_code == 400

    def test_reset_password_rejects_short_password(self, client, make_user):
        user = make_user()
        token = security.create_password_reset_token({"sub": user.email})
        response = client.post(
            "/auth/reset-password", json={"token": token, "password": "short"}
        )
        assert response.status_code == 422


class TestRoleManagement:
    def test_admin_can_change_role(self, client, make_user, auth_headers):
        admin = make_user(username="root", email="root@example.com", role="admin")
        target = make_user(username="user1", email="user1@example.com")
        response = client.patch(
            f"/admin/users/{target.id}/role",
            json={"role": "admin"},
            headers=auth_headers(admin),
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_regular_user_cannot_change_role(self, client, make_user, auth_headers):
        user = make_user(username="user1", email="user1@example.com")
        target = make_user(username="user2", email="user2@example.com")
        response = client.patch(
            f"/admin/users/{target.id}/role",
            json={"role": "admin"},
            headers=auth_headers(user),
        )
        assert response.status_code == 403

    def test_change_role_missing_user_returns_404(self, client, make_user, auth_headers):
        admin = make_user(username="root", email="root@example.com", role="admin")
        response = client.patch(
            "/admin/users/9999/role", json={"role": "admin"}, headers=auth_headers(admin)
        )
        assert response.status_code == 404

    def test_invalid_role_value_rejected(self, client, make_user, auth_headers):
        admin = make_user(username="root", email="root@example.com", role="admin")
        target = make_user(username="user1", email="user1@example.com")
        response = client.patch(
            f"/admin/users/{target.id}/role",
            json={"role": "superadmin"},
            headers=auth_headers(admin),
        )
        assert response.status_code == 422


class TestAvatar:
    def test_admin_can_change_own_avatar(self, client, make_user, auth_headers):
        admin = make_user(username="root", email="root@example.com", role="admin")
        response = client.patch(
            "/users/avatar",
            headers=auth_headers(admin),
            files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["avatar"] == "https://cloudinary.test/fake-avatar.png"

    def test_regular_user_cannot_change_avatar(self, client, make_user, auth_headers):
        user = make_user()
        response = client.patch(
            "/users/avatar",
            headers=auth_headers(user),
            files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
        )
        assert response.status_code == 403

    def test_avatar_rejects_non_image_file(self, client, make_user, auth_headers):
        admin = make_user(role="admin")
        response = client.patch(
            "/users/avatar",
            headers=auth_headers(admin),
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400