import pytest
from minio import Minio
from minio.error import S3Error
from ragcommerce_api.media import MinioMediaStore


@pytest.mark.parametrize("code", ["AccessDenied", "BucketAlreadyExists"])
def test_startup_preserves_storage_errors_other_than_the_owned_bucket_race(monkeypatch, code):
    error = S3Error(
        response=None,
        code=code,
        message="storage boundary failure",
        resource="/test-bucket",
        request_id="test",
        host_id="test",
    )
    monkeypatch.setattr(Minio, "bucket_exists", lambda *_: False)

    def fail_create(*_):
        raise error

    monkeypatch.setattr(Minio, "make_bucket", fail_create)
    with pytest.raises(S3Error) as caught:
        MinioMediaStore("unused", "127.0.0.1:9000", "test", "test-not-live")
    assert caught.value is error
