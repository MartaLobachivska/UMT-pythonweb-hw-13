from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    phone: str = Field(min_length=3, max_length=30)
    birthday: date
    additional_data: str | None = Field(default=None, max_length=500)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    birthday: date | None = None
    additional_data: str | None = Field(default=None, max_length=500)


class ContactResponse(ContactBase):
    id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    avatar: str | None
    confirmed: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
