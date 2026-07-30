# UMT Python Web — Homework 11

REST API for private contacts with registration, JWT authorization, email verification, Redis rate limiting, CORS, and Cloudinary avatars.

## Start

1. Copy `.env.example` to `.env` and fill in every `your_...` / `replace_...` value. Do not commit `.env`.
2. From this directory run `docker compose up --build`.
3. Open `http://localhost:8000/docs`.

The database and Redis run in Docker. `DATABASE_URL` must use host `db` when the API runs in Docker, as shown in `.env.example`.

## Main flow

1. `POST /auth/signup` with JSON:
   ```json
   {"username":"anna","email":"anna@example.com","password":"strong-password"}
   ```
   It returns `201` and sends an email confirmation link in the background.
2. Open the received confirmation link, or call `GET /auth/confirmed_email?token=...`.
3. `POST /auth/login` is **form data**, not JSON: `username` (username or email) and `password`. Copy `access_token` from its response.
4. In Swagger click **Authorize** and paste the token, then use contact endpoints. Search and birthday routes remain `/search/` and `/birthdays/`.

`GET /users/me` (and alias `/me`) is limited to 5 requests per minute per client. The avatar endpoint is `PATCH /users/avatar` and takes a multipart form field named `file`.

## Submission checks

- `POST /auth/signup` with an existing email returns `409`.
- Password is stored only in `hashed_password`.
- Every contact route requires `Authorization: Bearer <access_token>`.
- SQL filters contacts by both `id` and current `user_id`; users cannot access each other’s contacts.
- SMTP, Cloudinary, JWT and database values are in `.env`, never source code.
