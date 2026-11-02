import os
import secrets
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    APP_ROOT_PATH = os.environ.get("APP_ROOT_PATH", "").rstrip("/")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB upload cap

    # GSAP's Gateway forwards the signed-in user's email in this header; the app denies
    # any request missing it or outside ALLOWED_EMAIL_DOMAIN. Only disable this for local
    # dev (no Gateway in front) -- never in a deployed environment.
    REQUIRE_GSAP_AUTH = os.environ.get("REQUIRE_GSAP_AUTH", "true").lower() == "true"
    GSAP_AUTH_EMAIL_HEADER = "X-Auth-Request-Email"
    ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "akamai.com")
    MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "5"))
    MAX_PROPERTIES_PER_JOB = int(os.environ.get("MAX_PROPERTIES_PER_JOB", "1000"))
    WTF_CSRF_TIME_LIMIT = None

    CREDENTIAL_TTL_SECONDS = int(os.environ.get("CREDENTIAL_TTL_SECONDS", "3600"))

    # The session cookie only ever carries a random reference id (cred_id),
    # HMAC-signed by Flask/itsdangerous using SECRET_KEY -- never the credentials themselves.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=CREDENTIAL_TTL_SECONDS)
