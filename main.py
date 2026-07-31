from contextlib import asynccontextmanager
from typing import Annotated

import cloudinary
import cloudinary.uploader
import models
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from redis.asyncio import Redis
from sqlalchemy.orm import Session

import crud
import schemas
from cache import cache_user, get_redis, invalidate_user_cache
from config import settings
from database import Base, engine, get_db
from email_service import send_password_reset_email, send_verification_email
from security import (
    create_access_token,
    create_refresh_token,
    get_current_admin_user,
    get_current_user,
    get_email_from_token,
    get_password_hash,
    verify_password,
)

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    app.state.redis = redis
    await FastAPILimiter.init(redis)
    yield
    await redis.aclose()


app = FastAPI(title="Contacts API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[schemas.CachedUser, Depends(get_current_user)]
CurrentAdmin = Annotated[schemas.CachedUser, Depends(get_current_admin_user)]


@app.get("/")
def root():
    """Return a small health response for the API root URL."""
    return {"message": "Contacts API is running"}


@app.post("/auth/signup", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user: schemas.UserCreate, background_tasks: BackgroundTasks, db: DB):
    """Register a unique user and asynchronously request email verification."""
    if crud.get_user_by_email(db, str(user.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if crud.get_user_by_username(db, user.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")
    new_user = crud.create_user(db, user, get_password_hash(user.password))
    background_tasks.add_task(send_verification_email, new_user.email, new_user.username)
    return new_user


@app.post("/auth/login", response_model=schemas.Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DB,
    redis: Annotated[Redis, Depends(get_redis)],
):
    """Verify credentials, cache the user, and issue access/refresh JWT tokens."""
    # OAuth2 form uses the field name "username"; it accepts either username or email here.
    user = crud.get_user_by_username(db, form_data.username) or crud.get_user_by_email(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await cache_user(redis, schemas.CachedUser.model_validate(user))
    token_data = {"sub": user.email, "user_id": user.id}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }


@app.post("/auth/refresh", response_model=schemas.Token)
def refresh_access_token(payload: schemas.RefreshTokenRequest):
    """Exchange a valid refresh token for a newly signed token pair."""
    from jose import JWTError, jwt

    try:
        decoded = jwt.decode(
            payload.refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        email = decoded.get("sub")
        user_id = decoded.get("user_id")
        if decoded.get("token_type") != "refresh" or not isinstance(email, str) or not isinstance(user_id, int):
            raise JWTError
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    token_data = {"sub": email, "user_id": user_id}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }


@app.get("/auth/confirmed_email")
def confirm_email(token: str, db: DB):
    """Confirm an account after validating the token delivered by email."""
    email = get_email_from_token(token, "verify_email")
    if email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token")
    user = crud.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.confirmed:
        return {"message": "Email already confirmed"}
    crud.confirm_user_email(db, user)
    return {"message": "Email confirmed"}


@app.post("/auth/request_email")
async def request_email_verification(email: str, background_tasks: BackgroundTasks, db: DB):
    """Resend verification without revealing whether an account exists."""
    user = crud.get_user_by_email(db, email)
    if user is None:
        return {"message": "If this email exists, a verification email will be sent"}
    if user.confirmed:
        return {"message": "Email already confirmed"}
    background_tasks.add_task(send_verification_email, user.email, user.username)
    return {"message": "Verification email sent"}


@app.post("/auth/request-password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: schemas.PasswordResetRequest, background_tasks: BackgroundTasks, db: DB
):
    """Request a reset email while avoiding account-enumeration leaks."""
    user = crud.get_user_by_email(db, str(payload.email))
    if user is not None:
        background_tasks.add_task(send_password_reset_email, user.email, user.username)
    return {"message": "If this email exists, a password-reset email will be sent"}


@app.post("/auth/reset-password")
async def reset_password(
    payload: schemas.PasswordReset,
    db: DB,
    redis: Annotated[Redis, Depends(get_redis)],
):
    """Set a new password from a valid one-time-purpose reset token."""
    email = get_email_from_token(payload.token, "password_reset")
    if email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    user = crud.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
    crud.update_user_password(db, user, get_password_hash(payload.password))
    await invalidate_user_cache(redis, user.id)
    return {"message": "Password updated successfully"}


@app.get("/users/me", response_model=schemas.CachedUser, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
@app.get("/me", response_model=schemas.CachedUser, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def read_me(current_user: CurrentUser):
    """Return the authenticated user, normally served from Redis cache."""
    return current_user


@app.patch("/users/avatar", response_model=schemas.UserResponse)
async def update_avatar(
    current_user: CurrentAdmin,
    db: DB,
    redis: Annotated[Redis, Depends(get_redis)],
    file: Annotated[UploadFile, File()],
):
    """Upload the current user's image and invalidate stale cached profile data."""
    if file.content_type is None or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed")
    image = await file.read()
    if len(image) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image must be at most 5 MB")
    result = cloudinary.uploader.upload(image, folder="contacts_api_avatars")
    user = db.get(models.User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    updated_user = crud.update_user_avatar(db, user, result["secure_url"])
    await invalidate_user_cache(redis, updated_user.id)
    return updated_user


@app.patch("/admin/users/{user_id}/role", response_model=schemas.UserResponse)
async def change_user_role(
    user_id: int,
    payload: schemas.UserRoleUpdate,
    _: CurrentAdmin,
    db: DB,
    redis: Annotated[Redis, Depends(get_redis)],
):
    """Allow an administrator to grant or revoke the administrator role."""
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updated_user = crud.update_user_role(db, user, payload.role)
    await invalidate_user_cache(redis, updated_user.id)
    return updated_user


@app.post("/contacts/", response_model=schemas.ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(contact: schemas.ContactCreate, db: DB, current_user: CurrentUser):
    """Create a new contact owned by the authenticated user."""
    return crud.create_contact(db, contact, current_user.id)


@app.get("/contacts/", response_model=list[schemas.ContactResponse])
def read_contacts(
    current_user: CurrentUser,
    db: DB,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """List the authenticated user's contacts, paginated with skip/limit."""
    return crud.get_contacts(db, current_user.id, skip, limit)


@app.get("/contacts/{contact_id}", response_model=schemas.ContactResponse)
def read_contact(contact_id: int, current_user: CurrentUser, db: DB):
    """Fetch a single contact owned by the authenticated user, or 404."""
    contact = crud.get_contact(db, contact_id, current_user.id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@app.put("/contacts/{contact_id}", response_model=schemas.ContactResponse)
def update_contact(contact_id: int, contact: schemas.ContactUpdate, current_user: CurrentUser, db: DB):
    """Partially update a contact owned by the authenticated user, or 404."""
    updated = crud.update_contact(db, contact_id, current_user.id, contact)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return updated


@app.delete("/contacts/{contact_id}", response_model=schemas.ContactResponse)
def delete_contact(contact_id: int, current_user: CurrentUser, db: DB):
    """Delete a contact owned by the authenticated user, or 404."""
    deleted = crud.delete_contact(db, contact_id, current_user.id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return deleted


@app.get("/search/", response_model=list[schemas.ContactResponse])
def search_contacts(
    current_user: CurrentUser,
    db: DB,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
):
    """Search the authenticated user's contacts by partial name/email match."""
    return crud.search_contacts(db, current_user.id, first_name, last_name, email)


@app.get("/birthdays/", response_model=list[schemas.ContactResponse])
def upcoming_birthdays(current_user: CurrentUser, db: DB):
    """List contacts of the authenticated user with a birthday in the next 7 days."""
    return crud.get_upcoming_birthdays(db, current_user.id)