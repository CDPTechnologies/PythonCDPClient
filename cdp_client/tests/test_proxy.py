"""Unit tests for proxy logic that manual integration tests cannot exercise.

Most behavioural verification of proxy mode (sibling lifecycle, primary
restart, late discovery, value subscription resume) lives in the manual
test scripts at the repo root. These unit tests cover only the small
set of pure-logic branches that are awkward to drive from a live system:

  - ServiceTransport handshake timeout (uses threading.Timer; hard to
    trigger reliably against a real server)
  - Sibling key parsing edge cases (IPv4, IPv6, hostname)
  - find_proxy_service metadata matching
  - supports_proxy_protocol version gate
"""

from cdp_client import cdp
from cdp_client import cdp_pb2 as proto
import unittest
import mock


def make_websocket_proxy_service(service_id, addr, port):
    info = proto.ServiceInfo()
    info.service_id = service_id
    info.type = 'websocketproxy'
    info.metadata['proxy_type'] = 'studioapi'
    info.metadata['ip_address'] = addr
    info.metadata['port'] = str(port)
    return info


class ServiceTransportTimeoutTester(unittest.TestCase):
    def setUp(self):
        self._primary = mock.MagicMock()
        self._primary._service_instances = {'7:0': None}
        self._transport = cdp.ServiceTransport(self._primary, 7, 0)
        self._primary._service_instances['7:0'] = self._transport
        self._on_close_calls = []
        self._on_error_calls = []
        self._transport.on_close = lambda ws: self._on_close_calls.append(ws)
        self._transport.on_error = lambda ws, err: self._on_error_calls.append(err)

    def test_connect_starts_timer(self):
        self._transport.connect()
        self.assertIsNotNone(self._transport._connect_timer)
        self._transport._cancel_connect_timer()

    def test_eConnected_cancels_timer(self):
        self._transport.connect()
        msg = proto.ServiceMessage()
        msg.kind = proto.ServiceMessage.eConnected
        self._transport.on_service_message(msg)
        self.assertIsNone(self._transport._connect_timer)

    def test_close_cancels_timer(self):
        self._transport.connect()
        self._transport.close()
        self.assertIsNone(self._transport._connect_timer)

    def test_handle_connect_timeout_marks_closed_and_fires_callbacks(self):
        self._transport._handle_connect_timeout()
        self.assertTrue(self._transport._is_closed)
        self.assertEqual(self._on_error_calls, ['Proxy handshake timeout'])
        self.assertEqual(len(self._on_close_calls), 1)
        self.assertNotIn('7:0', self._primary._service_instances)

    def test_handle_connect_timeout_noop_when_already_connected(self):
        self._transport._is_connected = True
        self._transport._handle_connect_timeout()
        self.assertFalse(self._transport._is_closed)
        self.assertEqual(self._on_error_calls, [])

    def test_handle_connect_timeout_noop_when_already_closed(self):
        self._transport._is_closed = True
        self._transport._handle_connect_timeout()
        self.assertEqual(self._on_error_calls, [])
        self.assertEqual(self._on_close_calls, [])


class SiblingKeyParsingTester(unittest.TestCase):
    def setUp(self):
        connection = mock.MagicMock()
        connection._sibling_connections = {}
        self._tree = cdp.NodeTree(connection)

    def test_split_ipv4_key(self):
        addr, port = self._tree._split_sibling_key('192.168.1.10:7689')
        self.assertEqual(addr, '192.168.1.10')
        self.assertEqual(port, 7689)

    def test_split_hostname_key(self):
        addr, port = self._tree._split_sibling_key('host.example.com:7689')
        self.assertEqual(addr, 'host.example.com')
        self.assertEqual(port, 7689)

    def test_split_ipv6_key(self):
        addr, port = self._tree._split_sibling_key('::1:7689')
        self.assertEqual(addr, '::1')
        self.assertEqual(port, 7689)


class ServiceProxyDiscoveryTester(unittest.TestCase):
    def setUp(self):
        self._connection = cdp.Connection("foo", "bar", False)

    def tearDown(self):
        self._connection._auto_reconnect = False

    def test_find_proxy_service_matches_metadata(self):
        service = make_websocket_proxy_service(7, '10.0.0.1', 7690)
        self._connection._available_services[service.service_id] = service
        found = self._connection.find_proxy_service('10.0.0.1', 7690)
        self.assertIsNotNone(found)
        self.assertEqual(found.service_id, 7)

    def test_find_proxy_service_returns_none_when_no_match(self):
        service = make_websocket_proxy_service(7, '10.0.0.1', 7690)
        self._connection._available_services[service.service_id] = service
        self.assertIsNone(self._connection.find_proxy_service('10.0.0.2', 7690))
        self.assertIsNone(self._connection.find_proxy_service('10.0.0.1', 7691))

    def test_supports_proxy_protocol_requires_compat_version_4(self):
        self._connection._compat_version = 3
        self.assertFalse(self._connection.supports_proxy_protocol())
        self._connection._compat_version = 4
        self.assertTrue(self._connection.supports_proxy_protocol())
