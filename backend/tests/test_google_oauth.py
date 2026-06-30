import logging
import base64
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.db import Base, get_db
from app.main import app
from app.models.user import User
from app.routers import auth


class FakeTokenResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"id_token": "signed-google-token", "access_token": "google-access-token"}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.closed = True

    async def __aenter__(self):
        self.closed = False
        return self

    async def __aexit__(self, *args):
        self.closed = True
        return None

    async def post(self, *args, **kwargs):
        return FakeTokenResponse()


@pytest.fixture
def oauth_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(auth.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        settings, "GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback"
    )
    monkeypatch.setattr(
        settings, "GOOGLE_OAUTH_FRONTEND_SUCCESS_URL", "https://app.example.com/fa"
    )
    monkeypatch.setattr(
        settings, "GOOGLE_OAUTH_FRONTEND_ERROR_URL", "https://app.example.com/fa/login"
    )
    yield TestClient(app), Session
    app.dependency_overrides.clear()


def make_state(nonce="test-nonce"):
    return jwt.encode(
        {
            "locale": "fa",
            "nonce": nonce,
            "flow_id": "test-flow",
            "exp": datetime.utcnow() + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def test_google_callback_creates_user_and_returns_app_jwt(oauth_client, monkeypatch):
    client, Session = oauth_client

    async def valid_token(raw_id_token, client, flow_id, expected_nonce):
        assert client.closed is False
        assert expected_nonce == "test-nonce"
        return {
            "sub": "google-user-1",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Example User",
            "picture": "https://example.com/avatar.png",
            "nonce": "test-nonce",
        }

    monkeypatch.setattr(auth, "_validate_google_id_token", valid_token)
    state = make_state()
    response = client.get(
        f"/api/auth/google/callback?code=test-code&state={state}",
        cookies={auth.GOOGLE_STATE_COOKIE: state},
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    assert location.startswith("https://app.example.com/fa/auth/google/callback#access_token=")
    app_token = location.split("#access_token=", 1)[1]
    claims = jwt.decode(app_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    with Session() as db:
        user = db.query(User).filter(User.google_sub == "google-user-1").one()
        assert user.email == "user@example.com"
        assert claims["sub"] == str(user.id)


def test_google_callback_transport_failure_redirects_and_logs(oauth_client, monkeypatch, caplog):
    client, _ = oauth_client

    async def transport_failure(*args, **kwargs):
        raise httpx.TransportError("JWKS connection failed")

    monkeypatch.setattr(auth, "_validate_google_id_token", transport_failure)
    state = make_state()
    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        response = client.get(
            f"/api/auth/google/callback?code=test-code&state={state}",
            cookies={auth.GOOGLE_STATE_COOKIE: state},
            follow_redirects=False,
        )

    assert response.status_code in {302, 307}
    assert "google_error=token_validation_failed" in response.headers["location"]
    assert "error_message=JWKS connection failed" in caplog.text
    assert "signed-google-token" not in caplog.text


@pytest.mark.asyncio
async def test_google_id_token_is_verified_with_httpx_jwks(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    def b64uint(value):
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    google_jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "alg": "RS256",
        "use": "sig",
        "n": b64uint(public_numbers.n),
        "e": b64uint(public_numbers.e),
    }
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = jwt.encode(
        {
            "sub": "google-user-1",
            "aud": "test-client",
            "iss": "https://accounts.google.com",
            "exp": datetime.utcnow() + timedelta(minutes=5),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    class JwksResponse:
        headers = {"cache-control": "public, max-age=300"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [google_jwk]}

    class JwksClient:
        async def get(self, url):
            assert url == auth.GOOGLE_JWKS_URL
            return JwksResponse()

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    auth._google_jwks_cache.update(keys=[], expires_at=0.0)
    claims = await auth._validate_google_id_token(token, JwksClient(), "test-flow", "unused")
    assert claims["sub"] == "google-user-1"


def tokeninfo_claims(**overrides):
    claims = {
        "aud": "test-client",
        "iss": "https://accounts.google.com",
        "exp": str(int(datetime.now().timestamp()) + 300),
        "sub": "google-user-1",
        "email": "user@example.com",
        "email_verified": "true",
        "nonce": "expected-nonce",
    }
    claims.update(overrides)
    return claims


def raw_token_for_fallback(nonce="expected-nonce"):
    encode = lambda value: base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    return f'{encode({"alg": "RS256", "kid": "test-key"})}.{encode({"nonce": nonce})}.test-signature'


class TokeninfoResponse:
    def __init__(self, claims):
        self._claims = claims

    def raise_for_status(self):
        return None

    def json(self):
        return self._claims


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["403", "transport"])
async def test_jwks_failure_uses_tokeninfo_fallback(monkeypatch, failure, caplog):
    class FallbackClient:
        async def get(self, url):
            request = httpx.Request("GET", url)
            if failure == "403":
                response = httpx.Response(403, request=request)
                raise httpx.HTTPStatusError("403 Forbidden", request=request, response=response)
            raise httpx.ConnectError("proxy unavailable", request=request)

        async def post(self, url, **kwargs):
            assert url == auth.GOOGLE_TOKENINFO_URL
            assert "id_token" in kwargs["data"]
            return TokeninfoResponse(tokeninfo_claims())

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    auth._google_jwks_cache.update(keys=[], expires_at=0.0)
    with caplog.at_level(logging.INFO, logger="app.routers.auth"):
        claims = await auth._validate_google_id_token(
            raw_token_for_fallback(), FallbackClient(), "test-flow", "expected-nonce"
        )
    assert claims["sub"] == "google-user-1"
    assert "event=tokeninfo_validation_succeeded" in caplog.text
    assert "method=tokeninfo" in caplog.text


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"aud": "wrong-client"}, "audience"),
        ({"exp": "1"}, "expired"),
        ({"iss": "https://attacker.example"}, "issuer"),
        ({"sub": ""}, "subject"),
        ({"email": ""}, "email is missing"),
        ({"email_verified": "false"}, "not verified"),
    ],
)
def test_tokeninfo_claim_validation_rejects_invalid_claims(monkeypatch, overrides, error):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client")
    with pytest.raises(auth.JWTError, match=error):
        auth._validate_tokeninfo_claims(
            tokeninfo_claims(**overrides), raw_token_for_fallback(), "expected-nonce"
        )


def test_cors_origins_are_deduplicated():
    configured = Settings(
        CORS_ORIGINS="https://jibyar.digent24.com/,https://jibyar.digent24.com",
        _env_file=None,
    )
    assert configured.cors_origins_list == ["https://jibyar.digent24.com"]


def test_malformed_cors_origin_is_rejected():
    with pytest.raises(ValueError, match="Invalid CORS origin"):
        Settings(CORS_ORIGINS="http://https://jibyar.digent24.com", _env_file=None)
