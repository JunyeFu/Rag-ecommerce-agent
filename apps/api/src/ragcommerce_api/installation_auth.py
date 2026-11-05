"""Server-issued opaque installation credentials, never client-selected identities."""

import hashlib
import secrets
import sys
from contextlib import ExitStack
from uuid import uuid4

from ragcommerce_agent_runtime.postgres_connection import connect
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .service import DecisionConflict


def token_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class InMemoryInstallations:
    def __init__(self):
        self.credentials = {}

    def issue(self):
        owner, token = uuid4(), secrets.token_urlsafe(32)
        self.credentials[token_digest(token)] = owner
        return owner, token

    def authenticate(self, token):
        owner = self.credentials.get(token_digest(token))
        if owner is None:
            raise ValueError("invalid installation credential")
        return owner

    def delete_user(self, owner):
        keys = [k for k, v in self.credentials.items() if v == owner]
        for key in keys:
            del self.credentials[key]
        return len(keys)


class PostgresInstallations:
    def __init__(self, dsn):
        self.dsn = dsn

    def issue(self):
        owner, token = uuid4(), secrets.token_urlsafe(32)
        with connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO api_installations(owner_id,token_digest) VALUES (%s,%s)",
                (owner, token_digest(token)),
            )
        return owner, token

    def authenticate(self, token):
        with connect(self.dsn) as connection:
            row = connection.execute(
                "SELECT owner_id FROM api_installations WHERE token_digest=%s",
                (token_digest(token),),
            ).fetchone()
        if row is None:
            raise ValueError("invalid installation credential")
        return row[0]

    def delete_user(self, owner):
        with connect(self.dsn) as connection:
            return connection.execute(
                "DELETE FROM api_installations WHERE owner_id=%s", (owner,)
            ).rowcount


class InstallationAuth:
    def __init__(self, app, credentials, index, development_identity=False, ops_credentials=None):
        self.app, self.credentials, self.index = app, credentials, index
        self.development_identity = development_identity
        self.ops_credentials = ops_credentials

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in {
            "/health",
            "/docs",
            "/openapi.json",
            "/v1/installations",
        }:
            await self.app(scope, receive, send)
            return
        if self.development_identity and not Headers(scope=scope).get("authorization"):
            await self.app(scope, receive, send)
            return
        if scope["path"].startswith("/v1/ops"):
            if self.ops_credentials is None:
                await JSONResponse(
                    {"detail": "production operations identity is not configured"}, 503
                )(scope, receive, send)
                return
            authorization = Headers(scope=scope).get("authorization", "")
            try:
                if not authorization.startswith("Bearer "):
                    raise ValueError("operations credential required")
                actor = self.ops_credentials.authenticate(authorization[7:])
            except ValueError as exc:
                await JSONResponse({"detail": str(exc)}, 401)(scope, receive, send)
                return
            scope = dict(scope)
            scope["headers"] = [
                (k, v)
                for k, v in scope["headers"]
                if k.lower() not in {b"x-ops-role", b"x-ops-actor-id"}
            ] + [(b"x-ops-role", actor.role.encode()), (b"x-ops-actor-id", actor.actor_id.encode())]
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        stack = ExitStack()
        try:
            if not authorization.startswith("Bearer ") or self.credentials is None:
                raise ValueError("installation credential required")
            token = authorization[7:]
            owner = self.credentials.authenticate(token)
            if self.index is not None and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                stack.enter_context(self.index.owner_guard(owner, blocking=False))
                # A request queued before erasure cannot use a revoked credential.
                if self.credentials.authenticate(token) != owner:
                    raise ValueError("invalid installation credential")
        except (ValueError, DecisionConflict) as exc:
            stack.close()
            await JSONResponse(
                {"detail": str(exc)}, 409 if isinstance(exc, DecisionConflict) else 401
            )(scope, receive, send)
            return
        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"x-user-id"] + [
            (b"x-user-id", str(owner).encode())
        ]
        try:
            await self.app(scope, receive, send)
        finally:
            stack.__exit__(*sys.exc_info())
