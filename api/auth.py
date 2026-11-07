import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, AuditLog

SECRET = os.environ.get("AGRISAT_SECRET", "dev-secret-a-changer-en-production")
ALGO = "HS256"
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000)
    return hmac.compare_digest(dk.hex(), h)


def create_token(user: User) -> str:
    payload = {"sub": user.username, "role": user.role, "exp": datetime.utcnow() + timedelta(hours=12)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
    except JWTError:
        raise HTTPException(401, "Session invalide ou expirée")
    user = db.query(User).filter_by(username=data.get("sub")).first()
    if not user:
        raise HTTPException(401, "Utilisateur inconnu")
    return user


def require(*roles):
    def dep(user: User = Depends(current_user)):
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(403, "Action non autorisée pour ce rôle")
        return user
    return dep


def audit(db: Session, user: User | str, action: str, target: str, before=None, after=None):
    db.add(AuditLog(username=user if isinstance(user, str) else user.username, action=action,
                    target=target, before=before, after=after))
