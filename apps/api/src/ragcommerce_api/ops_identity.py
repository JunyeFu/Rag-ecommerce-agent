"""Operations credentials are provisioned by the server's administrator, never HTTP clients."""

import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

from ragcommerce_agent_runtime.postgres_connection import connect

from .installation_auth import token_digest
from .ops import ACTOR_PATTERN, ROLE_LEVEL, OpsActor


@dataclass(frozen=True)
class OpsCredential:
    id: UUID
    actor: OpsActor


def principal(actor_id: str, role: str) -> OpsActor:
    if not ACTOR_PATTERN.fullmatch(actor_id) or role not in ROLE_LEVEL:
        raise ValueError("invalid operations actor or role")
    return OpsActor(actor_id, role)


class InMemoryOpsCredentials:
    def __init__(self):
        self.credentials = {}

    def issue(self, actor_id: str, role: str):
        credential = OpsCredential(uuid4(), principal(actor_id, role))
        value = secrets.token_urlsafe(32)
        self.credentials[token_digest(value)] = credential
        return credential, value

    def authenticate(self, value: str) -> OpsActor:
        credential = self.credentials.get(token_digest(value))
        if credential is None:
            raise ValueError("invalid operations credential")
        return credential.actor

    def revoke(self, credential_id: UUID):
        for key, credential in list(self.credentials.items()):
            if credential.id == credential_id:
                del self.credentials[key]


class PostgresOpsCredentials:
    def __init__(self, dsn):
        self.dsn = dsn

    def issue(self, actor_id: str, role: str):
        credential = OpsCredential(uuid4(), principal(actor_id, role))
        value = secrets.token_urlsafe(32)
        with connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO ops_credentials(id,actor_id,role,token_digest) VALUES (%s,%s,%s,%s)",
                (credential.id, credential.actor.actor_id, role, token_digest(value)),
            )
        return credential, value

    def authenticate(self, value: str) -> OpsActor:
        with connect(self.dsn) as connection:
            row = connection.execute(
                "SELECT actor_id,role FROM ops_credentials WHERE token_digest=%s AND revoked=false",
                (token_digest(value),),
            ).fetchone()
        if row is None:
            raise ValueError("invalid operations credential")
        return principal(*row)

    def revoke(self, credential_id: UUID):
        with connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ops_credentials SET revoked=true WHERE id=%s", (credential_id,)
            )
