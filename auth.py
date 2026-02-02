from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer
import os
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
serializer = URLSafeSerializer(SECRET_KEY)

def create_session(username: str):
    return serializer.dumps({"username": username})

def verify_session(token: str):
    try:
        data = serializer.loads(token)
        return data.get("username")
    except Exception:
        return None

async def check_login(request: Request):
    token = request.cookies.get("session_token")
    user = verify_session(token) if token else None
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user
