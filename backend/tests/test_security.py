import pytest
from jose import JWTError

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_hash_and_verify_password():
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_decode_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_access_token("not-a-real-token")
