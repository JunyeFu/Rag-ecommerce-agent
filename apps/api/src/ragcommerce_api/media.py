"""Server-generated media references with signature, ownership, size and TTL checks."""

from __future__ import annotations

import hashlib
import os
import platform
import wave
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from ragcommerce_agent_runtime.postgres_connection import connect


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
}


def validate_media(
    content_type: str, content: bytes, image_limit=8 * 1024 * 1024, audio_limit=25 * 1024 * 1024
) -> tuple[str, str]:
    normalized = content_type.split(";", 1)[0].strip().lower()
    validator = SIGNATURES.get(normalized)
    if validator is None:
        raise MediaRejected("unsupported media type")
    kind = normalized.split("/", 1)[0]
    limit = image_limit if kind == "image" else audio_limit
    if len(content) > limit:
        raise MediaRejected(f"{kind} exceeds the configured size limit")
    if not content or not validator(content):
        raise MediaRejected("declared media type does not match file signature")
    try:
        if kind == "image":
            expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[normalized]
            with Image.open(BytesIO(content), formats=[expected]) as image:
                if image.width * image.height > 16_000_000 or getattr(image, "n_frames", 1) != 1:
                    raise MediaRejected("invalid media: image pixel/frame limit")
                image.verify()
            with Image.open(BytesIO(content), formats=[expected]) as image:
                image.load()
        else:
            with wave.open(BytesIO(content), "rb") as audio:
                frames = audio.getnframes()
                if not (
                    0 < frames <= 16000 * 60
                    and audio.getframerate() == 16000
                    and audio.getnchannels() == 1
                    and audio.getsampwidth() == 2
                ):
                    raise MediaRejected("invalid media: expected mono16k PCM16 WAV up to60seconds")
                if len(audio.readframes(frames)) != frames * 2:
                    raise MediaRejected("invalid media: truncated WAV frames")
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        EOFError,
        wave.Error,
        Image.DecompressionBombError,
    ) as exc:
        if isinstance(exc, MediaRejected):
            raise
        raise MediaRejected("invalid media: damaged content") from exc
    return normalized, kind


class InMemoryMediaStore:
    IMAGE_LIMIT = 8 * 1024 * 1024
    AUDIO_LIMIT = 25 * 1024 * 1024

    def __init__(self, ttl: timedelta = timedelta(hours=24)) -> None:
        self.ttl = ttl
        self.records: dict[UUID, tuple[StoredMedia, bytes]] = {}

    def create(self, owner_id: UUID, content_type: str, content: bytes) -> StoredMedia:
        normalized, kind = validate_media(content_type, content, self.IMAGE_LIMIT, self.AUDIO_LIMIT)
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

    def read_owned(self, owner_id: UUID, media_id: UUID) -> tuple[StoredMedia, bytes]:
        record = self.require_owned(owner_id, (media_id,))[0]
        return record, self.records[media_id][1]

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
        from minio.error import S3Error

        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if not self.client.bucket_exists(bucket):
            try:
                self.client.make_bucket(bucket)
            except S3Error as error:
                # Another API/Worker lane can create this same owned bucket first.
                if error.code != "BucketAlreadyOwnedByYou":
                    raise

    def create(self, owner_id: UUID, content_type: str, content: bytes) -> StoredMedia:
        normalized, kind = validate_media(content_type, content, self.IMAGE_LIMIT, self.AUDIO_LIMIT)
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
            with connect(self.dsn) as connection:
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
        with connect(self.dsn) as connection:
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

    def read_owned(self, owner_id: UUID, media_id: UUID) -> tuple[StoredMedia, bytes]:
        record = self.require_owned(owner_id, (media_id,))[0]
        response = self.client.get_object(self.bucket, f"{owner_id}/{media_id}")
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()
        self.require_owned(owner_id, (media_id,))
        return record, content

    def delete(self, owner_id: UUID, media_id: UUID) -> bool:
        with connect(self.dsn) as connection:
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
        with connect(self.dsn) as connection:
            rows = connection.execute(
                "SELECT object_key FROM api_media_objects WHERE owner_id=%s", (user_id,)
            ).fetchall()
            for (object_key,) in rows:
                self.client.remove_object(self.bucket, object_key)
            connection.execute("DELETE FROM api_media_objects WHERE owner_id=%s", (user_id,))
        return len(rows)

    def purge_expired(self, now: datetime | None = None) -> int:
        with connect(self.dsn) as connection:
            rows = connection.execute(
                """UPDATE api_media_objects SET deleted=true WHERE expires_at<=%s AND deleted=false
                RETURNING object_key""",
                (now or datetime.now(UTC),),
            ).fetchall()
        for (object_key,) in rows:
            self.client.remove_object(self.bucket, object_key)
        return len(rows)
