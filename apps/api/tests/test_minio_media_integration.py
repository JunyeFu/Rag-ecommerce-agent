from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from minio import Minio
from minio.error import S3Error
from ragcommerce_api.media import MinioMediaStore

pytestmark = pytest.mark.integration


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for MinIO integration")
    return value


def database_url() -> str:
    return required("API_DATABASE_URL").replace("postgresql+psycopg://", "postgresql://", 1)


def test_minio_media_create_delete_and_ttl_cleanup() -> None:
    dsn = database_url()
    endpoint = required("MINIO_ENDPOINT")
    access_key = required("MINIO_ACCESS_KEY")
    secret_key = required("MINIO_SECRET_KEY")
    bucket = f"ragcommerce-media-test-{uuid4().hex}"
    owner_id = uuid4()
    other_owner_id = uuid4()
    verifier = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"

    try:
        store = MinioMediaStore(dsn, endpoint, access_key, secret_key, bucket=bucket)
        active = store.create(owner_id, "image/png", content)

        assert store.require_owned(owner_id, (active.id,)) == (active,)
        assert store.read_owned(owner_id, active.id) == (active, content)
        with pytest.raises(KeyError):
            store.require_owned(other_owner_id, (active.id,))
        with pytest.raises(KeyError):
            store.read_owned(other_owner_id, active.id)
        assert verifier.stat_object(bucket, f"{owner_id}/{active.id}").size == len(content)

        assert store.delete(other_owner_id, active.id) is False
        assert store.delete(owner_id, active.id) is True
        with pytest.raises(S3Error):
            verifier.stat_object(bucket, f"{owner_id}/{active.id}")

        expiring = MinioMediaStore(
            dsn,
            endpoint,
            access_key,
            secret_key,
            bucket=bucket,
            ttl=timedelta(seconds=-1),
        )
        expired = expiring.create(owner_id, "image/png", content)
        with pytest.raises(KeyError):
            expiring.read_owned(owner_id, expired.id)
        assert expiring.purge_expired() == 1
        with pytest.raises(KeyError):
            expiring.require_owned(owner_id, (expired.id,))
        with pytest.raises(S3Error):
            verifier.stat_object(bucket, f"{owner_id}/{expired.id}")
    finally:
        with psycopg.connect(dsn) as connection:
            connection.execute("DELETE FROM api_media_objects WHERE owner_id=%s", (owner_id,))
        if verifier.bucket_exists(bucket):
            for item in verifier.list_objects(bucket, recursive=True):
                verifier.remove_object(bucket, item.object_name)
            verifier.remove_bucket(bucket)


def test_concurrent_minio_startup_keeps_both_media_stores_usable(monkeypatch):
    dsn = database_url()
    endpoint = required("MINIO_ENDPOINT")
    access_key = required("MINIO_ACCESS_KEY")
    secret_key = required("MINIO_SECRET_KEY")
    bucket = f"ragcommerce-startup-test-{uuid4().hex}"
    owner = uuid4()
    barrier = Barrier(2)
    bucket_exists = Minio.bucket_exists

    def observe_absence_together(client, name):
        exists = bucket_exists(client, name)
        if name == bucket and not exists:
            barrier.wait(timeout=10)
        return exists

    monkeypatch.setattr(Minio, "bucket_exists", observe_absence_together)
    verifier = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            stores = list(
                pool.map(
                    lambda _: MinioMediaStore(dsn, endpoint, access_key, secret_key, bucket=bucket),
                    range(2),
                )
            )
        content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
        media = stores[0].create(owner, "image/png", content)
        assert stores[1].read_owned(owner, media.id) == (media, content)
    finally:
        with psycopg.connect(dsn) as connection:
            connection.execute("DELETE FROM api_media_objects WHERE owner_id=%s", (owner,))
        if bucket_exists(verifier, bucket):
            for item in verifier.list_objects(bucket, recursive=True):
                verifier.remove_object(bucket, item.object_name)
            verifier.remove_bucket(bucket)
