from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from app.auth.security import decode_access_token
from app.config import getConnection

oauth2_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)):
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = payload["user_id"]
        version = payload["token_version"]

    except (ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, is_active, token_version
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )

            row = cur.fetchone()

    if row is None or not row[4]:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive"
        )

    if version != row[5]:
        raise HTTPException(
            status_code=401,
            detail="Token has been invalidated"
        )

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "role": row[3]
    }

def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    return current_user

def require_technician(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "TECHNICIAN":
        raise HTTPException(
            status_code=403,
            detail="Technician access required"
        )

    return current_user

def require_employee(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "EMPLOYEE":
        raise HTTPException(
            status_code=403,
            detail="Employee access required"
        )

    return current_user