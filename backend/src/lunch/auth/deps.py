from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from lunch.auth.service import user_from_token
from lunch.db import get_db
from lunch.errors import Unauthorized
from lunch.models import User

SESSION_COOKIE = "lunch_session"

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = await user_from_token(db, token) if token else None
    if user is None:
        raise Unauthorized("Not logged in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
