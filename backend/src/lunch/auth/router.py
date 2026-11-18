import html
import logging
from datetime import timedelta
from typing import Annotated, cast

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from lunch import ratelimit
from lunch.auth import service
from lunch.auth.deps import SESSION_COOKIE, CurrentUser, DbSession
from lunch.auth.schemas import (
    AccountOut,
    AccountUpdate,
    Credentials,
    ForgotPassword,
    PasswordChange,
    Providers,
    Registration,
    ResetPassword,
    UserOut,
)
from lunch.config import get_settings
from lunch.errors import DomainError, NotFound
from lunch.mailer import Mailer
from lunch.models import User
from lunch.ratelimit import client_ip

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE = "google"
# Remembered in the (signed) OAuth session cookie across the Google redirect.
_LINK_FLAG = "oauth_link_user"

oauth = OAuth()
if settings.google_enabled:
    oauth.register(
        name=GOOGLE,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email", "code_challenge_method": "S256"},
    )


def get_mailer(request: Request) -> Mailer:
    return cast(Mailer, request.app.state.mailer)


MailerDep = Annotated[Mailer, Depends(get_mailer)]


async def _start_session(db: DbSession, user: User, response: Response) -> None:
    ttl = timedelta(days=settings.session_ttl_days)
    token = await service.create_session(db, user, ttl)
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def _account(db: DbSession, user: User) -> AccountOut:
    identity = await service.oauth_identity(db, user.id, GOOGLE)
    return AccountOut(
        id=user.id,
        username=user.username,
        email=user.email,
        has_password=user.password_hash is not None,
        google_email=identity.email if identity else None,
        google_linked=identity is not None,
    )


def _require_google() -> None:
    if not settings.google_enabled:
        raise NotFound("Google sign-in is not configured on this server")


@router.get("/providers")
async def providers() -> Providers:
    return Providers(password=True, google=settings.google_enabled)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: Registration, request: Request, db: DbSession, response: Response
) -> UserOut:
    await ratelimit.enforce((ratelimit.REGISTER_PER_IP, client_ip(request)))
    user = await service.register(db, body.username, body.email, body.password)
    await _start_session(db, user, response)
    return UserOut.model_validate(user)


@router.post("/login")
async def login(body: Credentials, request: Request, db: DbSession, response: Response) -> UserOut:
    ip = client_ip(request)
    # Per IP + username, so nobody can lock a colleague out by guessing their password.
    await ratelimit.enforce(
        (ratelimit.LOGIN_PER_IP, ip), (ratelimit.LOGIN_PER_ACCOUNT, f"{ip}|{body.username}")
    )
    user = await service.authenticate(db, body.username, body.password)
    await _start_session(db, user, response)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DbSession, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await service.delete_session(db, token)
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/account")
async def account(user: CurrentUser, db: DbSession) -> AccountOut:
    return await _account(db, user)


@router.patch("/account")
async def update_account(body: AccountUpdate, user: CurrentUser, db: DbSession) -> AccountOut:
    await service.update_account(db, user, body.username, body.email)
    return await _account(db, user)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, db: DbSession
) -> None:
    await ratelimit.enforce((ratelimit.PASSWORD_CHANGE_PER_USER, str(user.id)))
    token = request.cookies.get(SESSION_COOKIE, "")
    await service.change_password(db, user, body.current_password, body.new_password, token)


async def _send_reset_email(mailer: Mailer, to: str, username: str, link: str) -> None:
    minutes = settings.reset_token_ttl_minutes
    text = (
        f"Hi {username},\n\nSomeone asked to reset your Lunch Roulette password. "
        f"Open this link within {minutes} minutes to choose a new one:\n\n{link}\n\n"
        "If it wasn't you, just ignore this email; your password stays the same."
    )
    page = f"""
      <div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto;color:#0f1530">
        <h2 style="margin-bottom:4px">Reset your password</h2>
        <p>Hi {html.escape(username)}, someone asked to reset your Lunch Roulette password.</p>
        <p><a href="{html.escape(link)}" style="display:inline-block;background:#525aff;color:#fff;
           padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600">
           Choose a new password</a></p>
        <p style="color:#5b6790;font-size:14px">
           The link works once and expires in {minutes} minutes.
           If it wasn't you, ignore this email.</p>
      </div>"""
    try:
        await mailer.send(to, "Reset your Lunch Roulette password", text, page)
    except Exception:
        log.exception("could not send password reset email")


@router.post("/password/forgot", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    body: ForgotPassword,
    request: Request,
    db: DbSession,
    mailer: MailerDep,
    background: BackgroundTasks,
) -> None:
    """Always answers 204, so the form can't be used to find out which emails have accounts.

    The email goes out in the background so response timing doesn't reveal it either.
    """
    # Per email too, so nobody can flood a colleague's inbox. Same answer either way.
    await ratelimit.enforce(
        (ratelimit.FORGOT_PER_IP, client_ip(request)), (ratelimit.FORGOT_PER_EMAIL, body.email)
    )
    ttl = timedelta(minutes=settings.reset_token_ttl_minutes)
    result = await service.create_reset_token(db, body.email, ttl)
    if result is None:
        return
    user, token = result
    origin = settings.public_url or str(request.base_url).rstrip("/")
    link = f"{origin}/reset-password?token={token}"
    assert user.email is not None
    background.add_task(_send_reset_email, mailer, user.email, user.username, link)


@router.post("/password/reset")
async def reset_password(
    body: ResetPassword, request: Request, db: DbSession, response: Response
) -> UserOut:
    await ratelimit.enforce((ratelimit.RESET_PER_IP, client_ip(request)))
    user = await service.reset_password(db, body.token, body.new_password)
    await _start_session(db, user, response)
    return UserOut.model_validate(user)


@router.delete("/google", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_google(user: CurrentUser, db: DbSession) -> None:
    await service.unlink_oauth(db, user, GOOGLE)


@router.get("/google/login")
async def google_login(request: Request, db: DbSession, link: bool = False) -> Response:
    """Starts the Google flow; with ?link=1 the Google account is attached to the logged-in user."""
    _require_google()
    request.session.pop(_LINK_FLAG, None)
    if link:
        token = request.cookies.get(SESSION_COOKIE)
        user = await service.user_from_token(db, token) if token else None
        if user is None:
            return RedirectResponse("/login")
        request.session[_LINK_FLAG] = user.id
    # Built from the incoming request (proxy headers included), so localhost and tunnels both work.
    redirect_uri = str(request.url_for("google_callback"))
    response: Response = await oauth.google.authorize_redirect(request, redirect_uri)
    return response


@router.get("/google/callback")
async def google_callback(request: Request, db: DbSession) -> Response:
    _require_google()
    link_user_id = request.session.pop(_LINK_FLAG, None)
    failure = "/settings?google=error" if link_user_id else "/login?error=google"
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        log.warning("google sign-in failed: %s", exc)
        return RedirectResponse(failure)
    claims = token["userinfo"]
    subject, email = str(claims["sub"]), claims.get("email")

    if link_user_id:
        user = await db.get(User, link_user_id)
        if user is None:
            return RedirectResponse("/login")
        try:
            await service.link_oauth(db, user, GOOGLE, subject, email)
        except DomainError as exc:
            log.info("google link refused: %s", exc.detail)
            return RedirectResponse("/settings?google=taken")
        return RedirectResponse("/settings?google=linked")

    user = await service.get_or_create_oauth_user(db, GOOGLE, subject, email)
    response = RedirectResponse("/")
    await _start_session(db, user, response)
    return response
