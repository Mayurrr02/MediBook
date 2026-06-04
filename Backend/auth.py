import hashlib
import jwt
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"


# HASH PASSWORD
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


# VERIFY PASSWORD
def verify_password(password, hashed):
    return hashlib.sha256(password.encode()).hexdigest() == hashed


# CREATE TOKEN
def create_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(days=1)

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# DECODE TOKEN
def decode_token(token: str):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])