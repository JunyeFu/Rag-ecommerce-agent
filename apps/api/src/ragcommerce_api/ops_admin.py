"""Local administrator command; it never exposes credential provisioning over HTTP."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from .ops_identity import PostgresOpsCredentials


def provision(store, actor_id, role, destination: Path):
    # Exclusive creation prevents replacing somebody else's credential file.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        credential, value = store.issue(actor_id, role)
        try:
            json.dump(
                {
                    "credential_id": str(credential.id),
                    "actor_id": actor_id,
                    "role": role,
                    "token": value,
                },
                stream,
            )
            stream.flush()
        except OSError:
            store.revoke(credential.id)
            raise
    return credential.id


def main():
    parser = argparse.ArgumentParser(
        description="Provision or revoke operations credentials from a trusted deployment shell"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("provision")
    create.add_argument("--actor-id", required=True)
    create.add_argument("--role", required=True, choices=["viewer", "reviewer", "admin"])
    create.add_argument("--credential-file", type=Path, required=True)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--credential-id", type=UUID, required=True)
    args = parser.parse_args()
    store = PostgresOpsCredentials(
        os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    )
    if args.command == "provision":
        identifier = provision(store, args.actor_id, args.role, args.credential_file)
        print(f"credential_id={identifier}; credential written to the requested protected file")
    else:
        store.revoke(args.credential_id)
        print("credential revoked")


if __name__ == "__main__":
    main()
