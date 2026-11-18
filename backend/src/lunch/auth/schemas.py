from pydantic import BaseModel, ConfigDict, EmailStr, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class Registration(Credentials):
    email: EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class Providers(BaseModel):
    password: bool
    google: bool


class AccountOut(BaseModel):
    id: int
    username: str
    email: str | None
    has_password: bool
    google_email: str | None
    google_linked: bool


class AccountUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    # Required only when the account already has a password.
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)
