"""Small, explicit normalization tables for the owned demo catalog."""

from __future__ import annotations

import re

_BRANDS = {
    "apple": "Apple",
    "apple苹果": "Apple",
    "苹果": "Apple",
    "xiaomi": "小米",
    "xiaomi小米": "小米",
    "小米": "小米",
    "huawei": "华为",
    "huawei华为": "华为",
    "华为": "华为",
}


def normalize_brand(value: str) -> str:
    key = re.sub(r"[\s/·_-]+", "", value).casefold()
    return _BRANDS.get(key, value.strip())
