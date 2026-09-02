# api/routers/notifications.py
#
# In-app notification endpoints.
# GET /api/v1/notifications/ — list recent notifications (last 50)
# POST /api/v1/notifications/read — mark notifications as read
# GET /api/v1/notifications/unread-count — unread count for bell badge

from fastapi import APIRouter, Request
from api.dependencies import CurrentUser, DBSession
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", summary="List recent notifications")
async def list_notifications(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    limit: int = 50,
):
    from sqlalchemy import select, desc
    from models.user import Notification

    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    notifications = result.scalars().all()

    return [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


@router.get("/unread-count", summary="Get unread notification count")
async def unread_count(
    current_user: CurrentUser,
    db: DBSession,
):
    from sqlalchemy import select, func
    from models.user import Notification

    result = await db.execute(
        select(func.count(Notification.id))
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    count = result.scalar() or 0
    return {"unread_count": count}


@router.post("/read", summary="Mark all notifications as read")
async def mark_all_read(
    current_user: CurrentUser,
    db: DBSession,
):
    from sqlalchemy import update
    from models.user import Notification

    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"message": "All notifications marked as read"}