"""
Oliver ingestion — Azure Functions HTTP trigger (Python v2 programming model).

This is the DEPLOYMENT host for the ingestion path. Power Automate ("when a new
email arrives" on the Oliver mailbox) POSTs the email here. The body is a thin
adapter: parse the request, build an InboundEmail, and delegate to the SAME
oliver_core.ingest.ingest_email handler the local FastAPI endpoint uses.

Because the logic lives in oliver-core, switching Power Automate from the local
FastAPI URL to this Function is a configuration/deployment change — no rewrite.

Deploy:  func azure functionapp publish <app-name>
Auth:    two layers.
         1. Function-level key (AuthLevel.FUNCTION) — transport gate at the Azure edge.
         2. App-layer bearer token (OLIVER_INGEST_TOKEN) — the SAME secret and check
            the local FastAPI host uses, so both hosts behave identically and the
            Entra-JWT upgrade lands in one place. Enforced only when
            OLIVER_REQUIRE_AUTH is on (off for local `func start`).
         Power Automate stores both as secure inputs / Key Vault refs.
Storage: set OLIVER_STORE=cosmos (+ endpoint/identity) in app settings.
"""

import os
import secrets

import azure.functions as func

from oliver_core.ingest import InboundEmail, ingest_email

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _ingest_authorized(req: func.HttpRequest) -> bool:
    """Mirror of app.auth.require_ingest_client for the deployed host.

    SEAM (Phase B): replace the compare_digest check with Entra JWT validation
    (signature/issuer/audience/app-role) when the caller moves to a managed identity.
    """
    if os.getenv("OLIVER_REQUIRE_AUTH", "").lower() not in ("1", "true", "yes"):
        return True  # local dev: don't gate
    expected = os.getenv("OLIVER_INGEST_TOKEN")
    if not expected:
        return False  # fail closed: enforcement on but no secret configured
    auth = req.headers.get("Authorization", "")
    presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return bool(presented) and secrets.compare_digest(presented, expected)


@app.route(route="ingest/email", methods=["POST"])
async def ingest_email_http(req: func.HttpRequest) -> func.HttpResponse:
    if not _ingest_authorized(req):
        return func.HttpResponse("invalid or missing ingest token", status_code=401)

    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    try:
        email = InboundEmail(**payload)
    except Exception as e:  # pydantic validation error
        return func.HttpResponse(f"Invalid email payload: {e}", status_code=422)

    try:
        result = await ingest_email(email, actor="power-automate")
    except ValueError as e:  # no assessable content
        return func.HttpResponse(str(e), status_code=422)

    status = 201 if result.status == "created" else 200
    return func.HttpResponse(
        result.model_dump_json(), status_code=status, mimetype="application/json"
    )
