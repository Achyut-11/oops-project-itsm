from app.exceptions import UserNotFound
from app.models.user import User

_SELECT_WITH_SKILLS = """
    SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at,
           u.years_of_experience,
           COALESCE(
               ARRAY_AGG(ts.skill) FILTER (WHERE ts.skill IS NOT NULL),
               ARRAY[]::VARCHAR[]
           ) AS skills
    FROM users u
    LEFT JOIN technician_skills ts ON u.id = ts.technician_id
"""


class UserRepository:
    def __init__(self, cur):
        self._cur = cur

    def list_all(self) -> list[User]:
        self._cur.execute(_SELECT_WITH_SKILLS + " GROUP BY u.id ORDER BY u.id")
        return [User.from_row(r) for r in self._cur.fetchall()]

    def get_by_id(self, user_id: int) -> User:
        self._cur.execute(
            _SELECT_WITH_SKILLS + " WHERE u.id = %s GROUP BY u.id", (user_id,)
        )
        row = self._cur.fetchone()
        if row is None:
            raise UserNotFound()
        return User.from_row(row)

    def email_exists(self, email: str) -> bool:
        self._cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        return self._cur.fetchone() is not None

    def is_active_technician_with_skill(self, user_id: int, skill: str) -> bool:
        self._cur.execute(
            """
            SELECT 1
            FROM users u
            JOIN technician_skills ts ON u.id = ts.technician_id
            WHERE u.id = %s AND u.role = 'TECHNICIAN'
              AND u.is_active = TRUE AND ts.skill = %s
            """,
            (user_id, skill),
        )
        return self._cur.fetchone() is not None

  
    def get_auth_by_email(self, email: str) -> dict | None:
        self._cur.execute(
            """
            SELECT id, name, email, role, password_hash, token_version, is_active
            FROM users WHERE email = %s
            """,
            (email,),
        )
        r = self._cur.fetchone()
        if r is None:
            return None
        return {"id": r[0], "name": r[1], "email": r[2], "role": r[3],
                "password_hash": r[4], "token_version": r[5], "is_active": r[6]}

    def get_password_hash(self, user_id: int) -> str | None:
        self._cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        row = self._cur.fetchone()
        return row[0] if row else None

    def change_password(self, user_id: int, new_hash: str) -> None:
        self._cur.execute(
            """
            UPDATE users
            SET password_hash = %s, token_version = token_version + 1
            WHERE id = %s
            """,
            (new_hash, user_id),
        )

    
    def create(self, name, email, role, years_of_experience, password_hash,
               skills=None) -> User:
        self._cur.execute(
            """
            INSERT INTO users (name, email, role, years_of_experience, password_hash)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, email, role, years_of_experience, password_hash),
        )
        user_id = self._cur.fetchone()[0]
        for skill in (skills or []):
            self._cur.execute(
                "INSERT INTO technician_skills (technician_id, skill) VALUES (%s, %s)",
                (user_id, skill),
            )
        return self.get_by_id(user_id)

    def admin_exists_locked(self) -> bool:
        """Takes the advisory lock so two simultaneous setups can't both pass."""
        self._cur.execute("SELECT pg_advisory_xact_lock(123456789)")
        self._cur.execute("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'ADMIN')")
        return self._cur.fetchone()[0]

    def create_admin(self, name, email, password_hash) -> User:
        self._cur.execute(
            """
            INSERT INTO users
                (name, email, role, years_of_experience, password_hash, is_active)
            VALUES (%s, %s, 'ADMIN', 0, %s, TRUE)
            RETURNING id
            """,
            (name, email, password_hash),
        )
        return self.get_by_id(self._cur.fetchone()[0])