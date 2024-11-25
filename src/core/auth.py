import uuid

from fastapi import Request


async def get_current_user(request: Request) -> str:

    user_id = request.session.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        request.session["user_id"] = user_id
    return user_id
