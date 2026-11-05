"""HEAD-only HTTPS redirect resolution with DNS results pinned to the socket peer."""

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from .security import SafeLinkPolicy
from .spi import ConnectorError, ConnectorErrorKind


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, *, timeout, context):
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("HTTPS requires certificate and hostname verification")
        super().__init__(host, 443, timeout=timeout, context=context)
        self.address = ipaddress.ip_address(address)

    def connect(self):
        family = socket.AF_INET6 if self.address.version == 6 else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as raw:
            raw.settimeout(self.timeout)
            # An IP literal goes directly to connect(); hostname DNS is never repeated here.
            target = (
                (str(self.address), 443, 0, 0)
                if family == socket.AF_INET6
                else (str(self.address), 443)
            )
            raw.connect(target)
            if ipaddress.ip_address(raw.getpeername()[0]) != self.address:
                raise SafeLinkPolicy._denied("connected peer differs from validated address")
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def resolve_addresses(host):
    return tuple(
        dict.fromkeys(
            row[4][0]
            for row in socket.getaddrinfo(
                host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        )
    )


class SafeHttpsResolver:
    def __init__(
        self, policy: SafeLinkPolicy, *, resolver=resolve_addresses, timeout=10, context=None
    ):
        self.policy, self.resolver, self.timeout = policy, resolver, timeout
        self.context = context or ssl.create_default_context()
        if not self.context.check_hostname or self.context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("HTTPS requires certificate and hostname verification")

    def resolve(self, url: str) -> str:
        chain = []
        while True:
            chain.append(url)
            try:
                self.policy.validate_fixture_chain(tuple(chain))
                parsed = urlsplit(url)
                host = self.policy._ascii_host(parsed.hostname or "")
                addresses = self.resolver(host)
                self.policy.validate_chain((url,), {host: addresses})
                connection = PinnedHTTPSConnection(
                    host, addresses[0], timeout=self.timeout, context=self.context
                )
                try:
                    path = parsed.path or "/"
                    if parsed.query:
                        path += "?" + parsed.query
                    # No cookies, credentials, proxy environment or automatic redirects.
                    connection.request("HEAD", path, headers={"Connection": "close"})
                    response = connection.getresponse()
                    status, location = response.status, response.getheader("Location")
                    response.close()
                finally:
                    connection.close()
            except ConnectorError:
                raise
            except (ValueError, OSError, http.client.HTTPException) as exc:
                raise ConnectorError(
                    ConnectorErrorKind.INVALID_RESPONSE,
                    "HTTPS link verification failed",
                    retryable=False,
                ) from exc
            if status in {301, 302, 303, 307, 308}:
                if not location:
                    raise ConnectorError(
                        ConnectorErrorKind.INVALID_RESPONSE,
                        "redirect missing Location",
                        retryable=False,
                    )
                url = urljoin(url, location)
                continue
            if 200 <= status < 300:
                return url
            raise ConnectorError(
                ConnectorErrorKind.INVALID_RESPONSE, "unexpected HTTPS link status", retryable=False
            )
