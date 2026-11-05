import ssl
from unittest.mock import MagicMock

import pytest
from ragcommerce_connectors.https_transport import PinnedHTTPSConnection, SafeHttpsResolver
from ragcommerce_connectors.security import SafeLinkPolicy
from ragcommerce_connectors.spi import ConnectorError

POLICY = SafeLinkPolicy(frozenset({"shop.example", "next.example"}))


def test_socket_connect_uses_validated_ip_and_original_hostname(monkeypatch):
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.getpeername.return_value = ("93.184.216.34", 443)
    factory = MagicMock(return_value=raw)
    monkeypatch.setattr("ragcommerce_connectors.https_transport.socket.socket", factory)
    context = MagicMock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
    connection = PinnedHTTPSConnection("shop.example", "93.184.216.34", timeout=2, context=context)
    connection.connect()
    raw.connect.assert_called_once_with(("93.184.216.34", 443))
    context.wrap_socket.assert_called_once_with(raw, server_hostname="shop.example")


def test_changed_socket_peer_is_rejected_before_tls(monkeypatch):
    raw = MagicMock()
    raw.__enter__.return_value = raw
    raw.getpeername.return_value = ("127.0.0.1", 443)
    monkeypatch.setattr("ragcommerce_connectors.https_transport.socket.socket", lambda *a: raw)
    context = MagicMock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
    with pytest.raises(ConnectorError):
        PinnedHTTPSConnection("shop.example", "93.184.216.34", timeout=2, context=context).connect()
    context.wrap_socket.assert_not_called()


@pytest.mark.parametrize(
    "addresses", [(), ("127.0.0.1",), ("93.184.216.34", "10.0.0.1"), ("not-an-ip",)]
)
def test_dns_invalidity_never_reaches_transport(monkeypatch, addresses):
    connection = MagicMock()
    monkeypatch.setattr("ragcommerce_connectors.https_transport.PinnedHTTPSConnection", connection)
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=lambda _: addresses).resolve("https://shop.example/item")
    connection.assert_not_called()


@pytest.mark.parametrize(
    "location",
    [
        "http://shop.example/item",
        "https://evil.example/item",
        "https://shop.example:8443/item",
        "https://user:pw@shop.example/item",
    ],
)
def test_redirect_authority_is_validated_before_next_dns(monkeypatch, location):
    response = MagicMock(status=302)
    response.getheader.return_value = location
    connection = MagicMock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(
        "ragcommerce_connectors.https_transport.PinnedHTTPSConnection", lambda *a, **k: connection
    )
    dns = MagicMock(return_value=("93.184.216.34",))
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=dns).resolve("https://shop.example/item")
    dns.assert_called_once_with("shop.example")


def test_each_redirect_resolves_anew_and_dns_rebinding_to_private_is_denied(monkeypatch):
    response = MagicMock(status=302)
    response.getheader.return_value = "/second"
    connection = MagicMock()
    connection.getresponse.return_value = response
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr("ragcommerce_connectors.https_transport.PinnedHTTPSConnection", factory)
    dns = MagicMock(side_effect=[("93.184.216.34",), ("127.0.0.1",)])
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=dns).resolve("https://shop.example/first")
    assert dns.call_count == 2 and factory.call_count == 1


def test_relative_redirect_is_bounded_without_forwarded_credentials(monkeypatch):
    response = MagicMock(status=302)
    response.getheader.return_value = "/loop"
    connection = MagicMock()
    connection.getresponse.return_value = response
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr("ragcommerce_connectors.https_transport.PinnedHTTPSConnection", factory)
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=lambda _: ("93.184.216.34",)).resolve(
            "https://shop.example/start"
        )
    assert factory.call_count == 4
    for call in connection.request.call_args_list:
        assert call.args[0] == "HEAD"
        assert call.kwargs["headers"] == {"Connection": "close"}


def test_certificate_checks_cannot_be_disabled():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    with pytest.raises(ValueError, match="hostname"):
        SafeHttpsResolver(POLICY, context=context)
