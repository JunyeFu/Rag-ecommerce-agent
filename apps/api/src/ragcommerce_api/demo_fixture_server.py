"""Explicit in-memory test server; its public test credentials grant no production access."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .demo import create_demo_app
from .installation_auth import token_digest
from .ops import OpsActor
from .ops_identity import InMemoryOpsCredentials, OpsCredential

credentials = InMemoryOpsCredentials()
for role in ("viewer", "reviewer"):
    actor = OpsActor(f"fixture-{role}", role)
    credentials.credentials[token_digest(f"test-only-ops-{role}")] = OpsCredential(
        uuid5(NAMESPACE_URL, actor.actor_id), actor
    )
app = create_demo_app(
    Path(__file__).resolve().parents[4] / "data/demo/catalog.v3.jsonl", ops_credentials=credentials
)
