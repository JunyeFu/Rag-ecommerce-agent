"""Server-generated media references with signature, ownership, size and TTL checks."""

from __future__ import annotations

import hashlib
import os
import platform
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import psycopg


class MediaRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StoredMedia:
    id: UUID
    owner_id: UUID
    kind: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    expires_at: datetime


SIGNATURES = {
    "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
    "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda value: (
        len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WEBP"
    ),
    "audio/wav": lambda value: (
        len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WAVE"
    ),
    "audio/mpeg": lambda value: (
        value.startswith(b"ID3")
        or (len(value) >= 2 and value[0] == 0xFF and value[1] & 0xE0 == 0xE0)
    ),
    "audio/ogg": lambda value: value.startswith(b"OggS"),
}


class InMemoryMediaStore:
    IMAGE_LIMIT = 8 * 1024 * 1024
    AUDIO_LIMIT = 25 * 1024 * 1024

    def __init__(self, ttl: timedelta = timedelta(hours=24)) -> None:
        self.ttl = ttl
        self.records: dict[UUID, tuple[StoredMedia, bytes]] = {}

    def create(self, owner_id: UUID, content_type: str, content: bytes) -> StoredMedia:
        normalized = content_type.split(";", 1)[0].strip().lower()
        validator = SIGNATURES.get(normalized)
        if validator is None:
            raise MediaRejected("unsupported media type")
        if not content or not validator(content):
            raise MediaRejected("declared media type does not match file signature")
        kind = normalized.split("/", 1)[0]
        limit = self.IMAGE_LIMIT if kind == "image" else self.AUDIO_LIMIT
        if len(content) > limit:
            raise MediaRejected(f"{kind} exceeds the configured size limit")
        now = datetime.now(UTC)
        record = StoredMedia(
            uuid4(),
            owner_id,
            kind,
            normalized,
            len(content),
            hashlib.sha256(content).hexdigest(),
            now,
            now + self.ttl,
        )
        self.records[record.id] = (record, bytes(content))
        return record

    def require_owned(self, owner_id: UUID, media_ids: tuple[UUID, ...]) -> tuple[StoredMedia, ...]:
        now = datetime.now(UTC)
        records: list[StoredMedia] = []
        for media_id in media_ids:
            value = self.records.get(media_id)
            if value is None or value[0].owner_id != owner_id or value[0].expires_at <= now:
                raise KeyError("media not found")
            records.append(value[0])
        return tuple(records)

    def delete(self, owner_id: UUID, media_id: UUID) -> bool:
        value = self.records.get(media_id)
        if value is None or value[0].owner_id != owner_id:
            return False
        del self.records[media_id]
        return True

    def delete_user(self, user_id: UUID) -> int:
        owned = [key for key, (record, _) in self.records.items() if record.owner_id == user_id]
        for key in owned:
            del self.records[key]
        return len(owned)

    def purge_expired(self, now: datetime | None = None) -> int:
        cutoff = now or datetime.now(UTC)
        expired = [key for key, (record, _) in self.records.items() if record.expires_at <= cutoff]
        for key in expired:
            del self.records[key]
        return len(expired)


class MinioMediaStore:
    """PostgreSQL metadata plus private MinIO objects with explicit TTL cleanup."""

    IMAGE_LIMIT = InMemoryMediaStore.IMAGE_LIMIT
    AUDIO_LIMIT = InMemoryMediaStore.AUDIO_LIMIT

    def __init__(
        self,
        dsn: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "ragcommerce-media",
        secure: bool = False,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self.dsn = dsn
        self.bucket = bucket
        self.ttl = ttl
        if os.name == "nt" and getattr(platform, "_uname_cache", None) is None:
            # MinIO builds a user-agent through platform.system(); WMI is unavailable on
            # some Windows development hosts, so cache only the non-business OS label.
            platform._uname_cache = platform.uname_result("Windows", "", "", "", "")
        from minio import Minio

        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def create(self, owner_id: UUID, content_type: str, content: bytes) -> StoredMedia:
        normalized = content_type.split(";", 1)[0].strip().lower()
        validator = SIGNATURES.get(normalized)
        if validator is None:
            raise MediaRejected("unsupported media type")
        if not content or not validator(content):
            raise MediaRejected("declared media type does not match file signature")
        kind = normalized.split("/", 1)[0]
        limit = self.IMAGE_LIMIT if kind == "image" else self.AUDIO_LIMIT
        if len(content) > limit:
            raise MediaRejected(f"{kind} exceeds the configured size limit")
        now = datetime.now(UTC)
        record = StoredMedia(
            uuid4(),
            owner_id,
            kind,
            normalized,
            len(content),
            hashlib.sha256(content).hexdigest(),
            now,
            now + self.ttl,
        )
        object_key = f"{owner_id}/{record.id}"
        self.client.put_object(
            self.bucket, object_key, BytesIO(content), len(content), content_type=normalized
        )
        try:
            with psycopg.connect(self.dsn) as connection:
                connection.execute(
                    """INSERT INTO api_media_objects(
                    id,owner_id,kind,content_type,size_bytes,content_sha256,object_key,
                    created_at,expires_at,deleted) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false)""",
                    (
                        record.id,
                        record.owner_id,
                        record.kind,
                        record.content_type,
                        record.size_bytes,
                        record.sha256,
                        object_key,
                        record.created_at,
                        record.expires_at,
                    ),
                )
        except Exception:
            self.client.remove_object(self.bucket, object_key)
            raise
        return record

    def require_owned(self, owner_id: UUID, media_ids: tuple[UUID, ...]) -> tuple[StoredMedia, ...]:
        if not media_ids:
            return ()
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """SELECT id,owner_id,kind,content_type,size_bytes,content_sha256,created_at,expires_at
                FROM api_media_objects WHERE owner_id=%s AND id=ANY(%s) AND deleted=false
                AND expires_at>%s""",
                (owner_id, list(media_ids), datetime.now(UTC)),
            ).fetchall()
        values = {row[0]: StoredMedia(*row) for row in rows}
        try:
            return tuple(values[media_id] for media_id in media_ids)
        except KeyError as exc:
            raise KeyError("media not found") from exc

    def delete(self, owner_id: UUID, media_id: UUID) -> bool:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """UPDATE api_media_objects SET deleted=true WHERE id=%s AND owner_id=%s
                AND deleted=false RETURNING object_key""",
                (media_id, owner_id),
            ).fetchone()
        if row is None:
            return False
        self.client.remove_object(self.bucket, row[0])
        return True

    def delete_user(self, user_id: UUID) -> int:
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """UPDATE api_media_objects SET deleted=true WHERE owner_id=%s AND deleted=false
                RETURNING object_key""",
                (user_id,),
            ).fetchall()
        for (object_key,) in rows:
            self.client.remove_object(self.bucket, object_key)
        return len(rows)

    def purge_expired(self, now: datetime | None = None) -> int:
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """UPDATE api_media_objects SET deleted=true WHERE expires_at<=%s AND deleted=false
                RETURNING object_key""",
                (now or datetime.now(UTC),),
            ).fetchall()
        for (object_key,) in rows:
            self.client.remove_object(self.bucket, object_key)
        return len(rows)
