from app.exceptions import NotificationNotFound
from app.models.notifications import Notification


class NotificationRepository:
    def __init__(self, cur):
        self._cur = cur

    def list_all(self) -> list[Notification]:
        self._cur.execute(
            f"SELECT {Notification.COLUMNS} FROM notifications ORDER BY created_at DESC, id DESC"
        )
        return [Notification.from_row(r) for r in self._cur.fetchall()]

    def list_for_user(self, user_id: int, unread_only: bool = False) -> list[Notification]:
        sql = f"SELECT {Notification.COLUMNS} FROM notifications WHERE user_id = %s"
        if unread_only:
            sql += " AND is_read = FALSE"
        sql += " ORDER BY created_at DESC, id DESC"
        self._cur.execute(sql, (user_id,))
        return [Notification.from_row(r) for r in self._cur.fetchall()]

    def mark_read(self, notification_id: int, user: dict) -> Notification:
        """Admins may mark any notification, others only their own.
        Marking an already-read notification is fine (idempotent)."""
        sql = f"UPDATE notifications SET is_read = TRUE WHERE id = %s"
        params = [notification_id]
        if user["role"] != "ADMIN":
            sql += " AND user_id = %s"
            params.append(user["id"])
        sql += f" RETURNING {Notification.COLUMNS}"
        self._cur.execute(sql, params)
        row = self._cur.fetchone()
        if row is None:
            raise NotificationNotFound()
        return Notification.from_row(row)