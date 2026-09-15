from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.database import get_db_connection

router = APIRouter(prefix="/api/auth", tags=["Authentication & RBAC"])

# Global in-memory active user for demo/testing
ACTIVE_USER_STATE = {
    "id": "usr_operator",
    "username": "operator",
    "full_name": "Data Capture Operator (John Doe)",
    "role": "operator"
}

class SwitchRoleRequest(BaseModel):
    role: str

@router.get("/users")
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY username ASC")
    users = [dict(u) for u in cursor.fetchall()]
    conn.close()
    return users

@router.get("/current")
def get_current_user():
    return ACTIVE_USER_STATE

@router.post("/switch")
def switch_user_role(req: SwitchRoleRequest):
    role = req.role.lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role = ?", (role,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail=f"No user found with role {role}")

    ACTIVE_USER_STATE["id"] = user["id"]
    ACTIVE_USER_STATE["username"] = user["username"]
    ACTIVE_USER_STATE["full_name"] = user["full_name"]
    ACTIVE_USER_STATE["role"] = user["role"]

    return ACTIVE_USER_STATE
