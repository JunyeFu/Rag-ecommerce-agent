"""
安全与异常单元测试

覆盖：
- validate_image_upload: 合法/非法 content_type / 超大文件
- ValidationError / AuthError 异常可抛出可捕获
"""
import pytest

from app.core.security import (
    validate_image_upload,
    ALLOWED_IMAGE_TYPES,
    MAX_UPLOAD_SIZE_BYTES,
)
from app.core.exceptions import ValidationError, AuthError, AppException

pytestmark = pytest.mark.unit


class TestValidateImageUpload:
    """图片上传校验"""

    def test_valid_content_type_and_size_passes(self):
        for ct in ALLOWED_IMAGE_TYPES:
            validate_image_upload(ct, 1024)
        validate_image_upload("image/jpeg", MAX_UPLOAD_SIZE_BYTES)

    def test_invalid_content_type_raises_value_error(self):
        with pytest.raises(ValueError, match="不支持的文件类型"):
            validate_image_upload("image/gif", 1024)

    def test_oversized_file_raises_value_error(self):
        with pytest.raises(ValueError, match="文件大小超过限制"):
            validate_image_upload("image/jpeg", MAX_UPLOAD_SIZE_BYTES + 1)


class TestExceptions:
    """自定义异常可抛出与捕获"""

    def test_validation_error_can_be_raised_and_caught(self):
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("字段缺失")
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == 4220
        assert "字段缺失" in exc_info.value.detail["message"]
        assert isinstance(exc_info.value, AppException)

    def test_auth_error_can_be_raised_and_caught(self):
        with pytest.raises(AuthError) as exc_info:
            raise AuthError("token 无效")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == 4010
        assert "token 无效" in exc_info.value.detail["message"]
