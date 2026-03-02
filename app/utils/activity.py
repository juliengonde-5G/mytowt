from sqlalchemy.ext.asyncio import AsyncSession
from app.models.activity import ActivityLog


async def log_activity(
    db: AsyncSession,
    user,
    module: str,
    action: str,
    resource_type: str = None,
    resource_id: int = None,
    detail: str = None,
):
    """Record an activity in the global journal."""
    entry = ActivityLog(
        user_id=user.id if user and hasattr(user, "id") else None,
        username=(user.full_name or user.username) if user and hasattr(user, "username") else (user if isinstance(user, str) else "Système"),
        module=module,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )
    db.add(entry)
