from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


# Information required when registering a user
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=5, max_length=100)
    password: str = Field(min_length=8)


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


# Token returned after successful login
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
