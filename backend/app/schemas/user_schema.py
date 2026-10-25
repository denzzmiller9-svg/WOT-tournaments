from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=4, max_length=40)
    email: EmailStr = Field(max_length=50)
    password: str = Field(min_length=12, max_length=128)


class WGRegistrationRequest(BaseModel):
    registration_token: str
    email: EmailStr = Field(max_length=50)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    wg_account_id: int | None = None
    is_active: bool


class UserNamePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str