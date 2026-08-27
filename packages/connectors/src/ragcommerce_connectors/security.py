"""SSRF- and redirect-safe affiliate link policy."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from .spi import ConnectorError, ConnectorErrorKind


@dataclass(frozen=True, slots=True)
class SafeLinkPolicy:
    allowed_hosts: frozenset[str]
    max_redirects: int = 3

    def __post_init__(self) -> None:
        normalized = frozenset(self._ascii_host(value) for value in self.allowed_hosts)
        object.__setattr__(self, "allowed_hosts", normalized)

    def validate_chain(
        self,
        urls: tuple[str, ...],
        resolved_addresses: Mapping[str, tuple[str, ...]] | None = None,
    ) -> str:
        if not urls or len(urls) - 1 > self.max_redirects:
            raise self._denied("redirect chain length denied")
        for url in urls:
            parsed = urlparse(url)
            host = self._ascii_host(parsed.hostname or "")
            if parsed.scheme != "https" or parsed.port not in (None, 443):
                raise self._denied("only HTTPS default port is allowed")
            if parsed.username or parsed.password or host not in self.allowed_hosts:
                raise self._denied("host or embedded authority denied")
            self._require_global_address(host)
            if resolved_addresses is not None:
                addresses = resolved_addresses.get(host)
                if not addresses:
                    raise self._denied("DNS resolution evidence is required")
                for address in addresses:
                    self._require_global_address(address)
        return urls[-1]

    @staticmethod
    def _ascii_host(value: str) -> str:
        try:
            return value.lower().rstrip(".").encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise SafeLinkPolicy._denied("invalid internationalized host") from exc

    @staticmethod
    def _require_global_address(value: str) -> None:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return
        if not address.is_global:
            raise SafeLinkPolicy._denied("non-public address denied")

    @staticmethod
    def _denied(message: str) -> ConnectorError:
        return ConnectorError(ConnectorErrorKind.POLICY_DENIED, message, retryable=False)
