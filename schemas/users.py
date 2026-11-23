from pydantic import BaseModel, ConfigDict, Field
from datetime import date as Date, datetime


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


# Information required when registering a user
class UserCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    username: str = Field(min_length=3, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str = Field(min_length=5, max_length=100)
    password: str = Field(min_length=8)
    phone_number: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=10, le=70)
    due_date: Date | None = None
    gestation_week: int | None = Field(default=None, ge=1, le=45)
    gravida: int | None = Field(default=None, ge=1)
    para: int | None = Field(default=None, ge=0)
    blood_type: str | None = Field(default=None, max_length=20)
    allergies: list[str] = Field(default_factory=list)
    medical_conditions: list[str] = Field(default_factory=list)


# Information allowed when updating a user
class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: str | None = Field(default=None, min_length=5, max_length=100)


# Information returned by the API
class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Information required when logging in
class UserLogin(BaseModel):
    identifier: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=100)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=8, max_length=128)


# Token returned after successful login
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
