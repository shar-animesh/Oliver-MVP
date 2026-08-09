"""Auth seam — resolves and (optionally) enforces the acting identity."""
import os
import secrets
from fastapi import Depends, Header, HTTPException


def _validate_bearer(token: str) -> str | None:
    # SEAM: production validates the JWT signature against Entra JWKS and reads the
    # identity claim. Here "actor:<name>" is a stand-in so the token path is exercised.
    if token.startswith("actor:"):
        return token[len("actor:"):] or None
    return None


def current_actor(authorization: str | None = Header(default=None),
                  x_oliver_actor: str | None = Header(default=None)) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        actor = _validate_bearer(authorization[7:].strip())
        if actor:
            return actor
    return x_oliver_actor or "anonymous"


def require_writer(actor: str = Depends(current_actor)) -> str:
    """Gate write operations. Enforcement is on in prod (OLIVER_REQUIRE_AUTH), off in local dev."""
    enforce = os.getenv("OLIVER_REQUIRE_AUTH", "").lower() in ("1", "true", "yes")
    if enforce and actor == "anonymous":
        raise HTTPException(status_code=401, detail="authentication required for write operations")
    return actor


def require_ingest_client(authorization: str | None = Header(default=None)) -> str:
    """
    Gate the MACHINE ingestion endpoint (Power Automate -> POST /ingest/email).

    This is different from require_writer, deliberately. require_writer resolves a
    *human* actor for Door-B attribution and can be satisfied by an X-Oliver-Actor
    header — that's fine for an audit label, but it is NOT access control. Power
    Automate is a service, so it must present a real *secret*, not a claimed name.

    Contract: Power Automate holds OLIVER_INGEST_TOKEN (stored as a Key Vault ref /
    secure input) and sends it as `Authorization: Bearer <token>`.

    Enforcement uses the same switch as the rest of the app:
      - OLIVER_REQUIRE_AUTH off  -> open (local dev; behaviour unchanged)
      - OLIVER_REQUIRE_AUTH on   -> a valid bearer token is mandatory (else 401)

    SEAM (Phase B): replace the compare_digest check below with Entra JWT validation
    — verify signature against the tenant JWKS, then check issuer, audience (this
    API's app-ID URI) and the granted app role. The wiring in ingest.py does not
    change when you do this; only the body of this function does.
    """
    enforce = os.getenv("OLIVER_REQUIRE_AUTH", "").lower() in ("1", "true", "yes")
    if not enforce:
        return "power-automate"  # local dev: attribute the record, don't gate it

    expected = os.getenv("OLIVER_INGEST_TOKEN")
    if not expected:
        # Fail closed: enforcement on but no secret configured is a deployment error,
        # not an open door.
        raise HTTPException(
            status_code=500,
            detail="ingest auth misconfigured: OLIVER_INGEST_TOKEN is not set",
        )

    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()

    # Constant-time compare avoids leaking the token through response timing.
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing ingest token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "power-automate"
