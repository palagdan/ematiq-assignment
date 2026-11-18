import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lunch.auth.security import hash_password, hash_token, new_session_token, verify_password
from lunch.errors import Conflict, DomainError, Unauthorized
from lunch.models import AuthSession, OAuthIdentity, PasswordResetToken, User

# Verifying against a dummy hash keeps login timing the same for unknown users.
_DUMMY_HASH = hash_password("not-a-real-password")


async def _check_free(db: AsyncSession, username: str | None, email: str | None) -> None:
    if username and await db.scalar(select(User.id).where(User.username == username)):
        raise Conflict("Username is already taken")
    if email and await db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists")


async def register(db: AsyncSession, username: str, email: str, password: str) -> User:
    email = email.lower()
    await _check_free(db, username, email)
    user = User(username=username, email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Username or email is already taken") from None
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.username == username))
    if user is None or user.password_hash is None:
        verify_password(password, _DUMMY_HASH)
        raise Unauthorized("Invalid username or password")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("Invalid username or password")
    return user


async def create_session(db: AsyncSession, user: User, ttl: timedelta) -> str:
    token = new_session_token()
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + ttl,
        )
    )
    await db.flush()
    return token


async def user_from_token(db: AsyncSession, token: str) -> User | None:
    session = await db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    return session.user if session else None


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))


async def _free_username(db: AsyncSession, wanted: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]", "", wanted)[:28] or "player"
    if len(base) < 3:
        base = f"{base}_player"[:28]
    candidate, n = base, 1
    while await db.scalar(select(User.id).where(User.username == candidate)) is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


async def get_or_create_oauth_user(
    db: AsyncSession, provider: str, subject: str, email: str | None
) -> User:
    identity = await db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider, OAuthIdentity.subject == subject
        )
    )
    if identity is not None:
        user = await db.get(User, identity.user_id)
        assert user is not None
        return user
    email = email.lower() if email else None
    email_free = (
        email is not None and await db.scalar(select(User.id).where(User.email == email)) is None
    )
    user = User(
        username=await _free_username(db, (email or "").split("@")[0]),
        email=email if email_free else None,
    )
    db.add(user)
    await db.flush()
    db.add(OAuthIdentity(user_id=user.id, provider=provider, subject=subject, email=email))
    await db.flush()
    return user


async def oauth_identity(db: AsyncSession, user_id: int, provider: str) -> OAuthIdentity | None:
    return await db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.user_id == user_id, OAuthIdentity.provider == provider
        )
    )


async def update_account(
    db: AsyncSession, user: User, username: str | None, email: str | None
) -> None:
    username = username if username and username != user.username else None
    email = email.lower() if email and email.lower() != user.email else None
    await _check_free(db, username, email)
    if username:
        user.username = username
    if email:
        user.email = email
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Username or email is already taken") from None


async def change_password(
    db: AsyncSession, user: User, current: str | None, new: str, keep_token: str
) -> None:
    """Set or change the password, then sign out every other session."""
    if user.password_hash is not None and (
        current is None or not verify_password(current, user.password_hash)
    ):
        raise Unauthorized("Current password is incorrect")
    user.password_hash = hash_password(new)
    await db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.token_hash != hash_token(keep_token)
        )
    )
    await db.commit()


async def link_oauth(
    db: AsyncSession, user: User, provider: str, subject: str, email: str | None
) -> None:
    email = email.lower() if email else None
    existing = await db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider, OAuthIdentity.subject == subject
        )
    )
    if existing is not None and existing.user_id != user.id:
        raise Conflict("This Google account is already used by another player")
    if existing is None:
        if await oauth_identity(db, user.id, provider) is not None:
            raise Conflict("Another Google account is already connected")
        db.add(OAuthIdentity(user_id=user.id, provider=provider, subject=subject, email=email))
    await db.commit()


async def unlink_oauth(db: AsyncSession, user: User, provider: str) -> None:
    if user.password_hash is None:
        raise DomainError("Set a password first, otherwise you could not sign in anymore")
    await db.execute(
        delete(OAuthIdentity).where(
            OAuthIdentity.user_id == user.id, OAuthIdentity.provider == provider
        )
    )
    await db.commit()


async def create_reset_token(
    db: AsyncSession, email: str, ttl: timedelta
) -> tuple[User, str] | None:
    """Returns the user and a fresh one-time token, or None if no account has this email."""
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        return None
    # Only the newest link works.
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    )
    token = new_session_token()
    db.add(
        PasswordResetToken(
            token_hash=hash_token(token), user_id=user.id, expires_at=datetime.now(UTC) + ttl
        )
    )
    await db.commit()
    return user, token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> User:
    """Uses up the token, sets the password and signs the user out everywhere."""
    now = datetime.now(UTC)
    reset = await db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hash_token(token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .with_for_update()
    )
    if reset is None:
        raise DomainError("This reset link is invalid or has expired. Request a new one.")
    user = await db.get(User, reset.user_id)
    assert user is not None
    reset.used_at = now
    user.password_hash = hash_password(new_password)
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await db.commit()
    return user


async def purge_expired(db: AsyncSession) -> tuple[int, int]:
    """Delete expired sessions and reset tokens (used tokens expire too). Returns the counts."""
    now = datetime.now(UTC)
    sessions = await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    tokens = await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.expires_at <= now)
    )
    await db.commit()
    return sessions.rowcount, tokens.rowcount  # type: ignore[attr-defined]
