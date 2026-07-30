from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import crud
from config import settings
from database import get_db
from models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    payload["token_type"] = token_type
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    return _create_token(data, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_email_token(data: dict) -> str:
    return _create_token(data, timedelta(hours=settings.VERIFY_EMAIL_EXPIRE_HOURS), "verify_email")


def get_email_from_token(token: str, expected_token_type: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("token_type") != expected_token_type:
            return None
        email = payload.get("sub")
        return email if isinstance(email, str) else None
    except JWTError:
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email = get_email_from_token(token, "access")
    if email is None:
        raise credentials_error
    user = crud.get_user_by_email(db, email)
    if user is None:
        raise credentials_error
    return user
