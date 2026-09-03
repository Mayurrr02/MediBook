import pytest
from auth import hash_password, verify_password, create_token, decode_token
from jose import JWTError


def test_password_hashing():
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_jwt_token_generation_and_decoding():
    payload = {"id": "user_id_12345", "role": "PATIENT"}
    token = create_token(payload)

    assert isinstance(token, str)
    decoded = decode_token(token)

    assert decoded["id"] == "user_id_12345"
    assert decoded["role"] == "PATIENT"
    assert "exp" in decoded


def test_invalid_jwt_token():
    with pytest.raises(JWTError):
        decode_token("invalid.token.structure")
