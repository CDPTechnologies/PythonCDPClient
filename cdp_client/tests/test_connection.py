from cdp_client import cdp
from cdp_client.tests import fake_data
from collections import namedtuple
import unittest
import mock


class ConnectionTester(unittest.TestCase):
    class TestNotificationListener(cdp.NotificationListener):
        def __init__(self, credentials=dict(), accept_app=True):
            self.application_acceptance_call_count = 0
            self.system_use_notification_received = None
            self.credentials_requested_call_count = 0
            self._credentials = credentials
            self._accept_app = accept_app

        def application_acceptance_requested(self, request):
            self.application_acceptance_call_count += 1
            self.system_use_notification_received = request.system_use_notification()
            if self._accept_app:
                request.accept()
            else:
                request.reject()

        def credentials_requested(self, request):
            self.credentials_requested_call_count += 1
            if self._credentials:
                request.accept(self._credentials)
            else:
                request.reject()


    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._connection = None

    def setUp(self):
        self._connection = cdp.Connection("foo", "bar", False)

    def tearDown(self):
        del self._connection

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_structure_request_when_not_connected(self, mock_send, mock_add):
        self._connection.send_structure_request(1, 'foo')
        self.assertTrue(mock_add.called)
        mock_send.assert_not_called()

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_structure_request_when_connected(self, mock_send, mock_add):
        self._connection._is_connected = True
        node_id = 1
        self._connection.send_structure_request(node_id, 'foo')
        self.assertTrue(mock_add.called)
        mock_send.assert_any_call(fake_data.create_structure_request(node_id).SerializeToString())

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_root_node_structure_request(self, mock_send, mock_add):
        self._connection._is_connected = True
        self._connection.send_structure_request(None, 'foo')
        self.assertTrue(mock_add.called)
        mock_send.assert_any_call(fake_data.create_structure_request().SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value_request(self, mock_send):
        node_id = 1
        self._connection.send_value_request(node_id)
        mock_send.assert_any_call(fake_data.create_value_request(node_id).SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value_unrequest(self, mock_send):
        node_id = 1
        self._connection.send_value_unrequest(node_id)
        mock_send.assert_any_call(fake_data.create_value_unrequest(node_id).SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value(self, mock_send):
        self._connection.send_value(fake_data.value1)
        mock_send.assert_any_call(fake_data.create_setter_request(fake_data.value1).SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'run_forever')
    def test_run_event_loop(self, mock_run_forever):
        self._connection.run_event_loop()
        mock_run_forever.assert_called_once_with(sslopt=dict())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'close')
    def test_closing(self, mock_close):
        self._connection.close()
        mock_close.assert_called_once_with()

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_connected_state_is_set_when_receiving_hello_message_with_correct_version(self, mock_send):
        self.assertFalse(self._connection._is_connected)
        self._connection._handle_hello_message(fake_data.create_valid_hello_response().SerializeToString())
        self.assertTrue(self._connection._is_connected)

    def test_connected_state_is_unset_when_receiving_hello_message_with_incorrect_version(self):
        self.assertFalse(self._connection._is_connected)
        self._connection._handle_hello_message(fake_data.create_invalid_hello_response().SerializeToString())
        self.assertFalse(self._connection._is_connected)

    @mock.patch.object(cdp.NodeTree, 'find_by_id')
    @mock.patch.object(cdp.Node, '_update_value')
    def test_node_updated_when_node_value_received(self, mock_update_value, mock_find_by_id):
        self._connection._is_connected = True
        mock_find_by_id.return_value = cdp.Node(None, self._connection, fake_data.app1_node)
        response = fake_data.create_value_response()
        self._connection._handle_container_message(response.SerializeToString())
        mock_update_value.assert_called_once_with(response.getter_response[0])

    @mock.patch.object(cdp.NodeTree, 'find_by_id')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_node_structure_requested_when_node_structure_change_received(self, mock_send, mock_find_by_id):
        self._connection._is_connected = True
        mock_find_by_id.return_value = cdp.Node(None, self._connection, fake_data.app1_node)
        response = fake_data.create_structure_change_response(fake_data.app1_node.info.node_id)
        request = fake_data.create_structure_change_request(response.structure_change_response[0])
        self._connection._handle_container_message(response.SerializeToString())
        mock_send.assert_any_call(request.SerializeToString())

    @mock.patch.object(cdp.Requests, 'clear')
    def test_requests_cleared_when_error_received(self, mock_clear):
        self._connection._handle_container_message(fake_data.create_error_response().SerializeToString())
        self.assertTrue(mock_clear.called)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    @mock.patch.object(cdp.time, 'time')
    def _test_time_difference_udpate(self, mock_time, mock_send):
        def side_effect(*args, **kwargs):
            nsec_in_sec = 1000000000
            sample = samples.pop(0)
            mock_time.side_effect = [initial_time + sample.ping, initial_time]
            self._connection._handle_container_message(fake_data.create_time_response(sample.diff * nsec_in_sec).SerializeToString())

        initial_time = 10
        mock_time.return_value = initial_time
        mock_send.side_effect = side_effect
        samples = []

        Sample = namedtuple('Sample', 'ping, diff')
        samples.append(Sample(20, 100))
        samples.append(Sample(10, 200)) #this should be selected as it has the best ping
        samples.append(Sample(30, 300))

        self._connection._update_time_difference()
        request = fake_data.create_time_request().SerializeToString()
        mock_send.assert_has_calls([mock.call(request), mock.call(request), mock.call(request)])
        self.assertEqual(self._connection.server_time_difference(), -185.0)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    @mock.patch.object(cdp.time, 'time')
    def test_time_difference_udpate_frequency(self, mock_time, mock_send):
        def side_effect(*args, **kwargs):
            self._connection._handle_container_message(fake_data.create_time_response(1).SerializeToString())

        mock_time.return_value = 10
        mock_send.side_effect = side_effect
        self._connection._update_time_difference()
        self.assertTrue(mock_send.called)
        mock_send.reset_mock()
        self._connection._update_time_difference()
        self.assertFalse(mock_send.called)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_accept_request_is_sent_when_hello_is_received(self, mock_send):
        self._connection._notification_listener = self.TestNotificationListener()

        self._connection._handle_hello_message(fake_data.create_valid_hello_response(system_use_notification='Notification')
                                               .SerializeToString())

        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 1)
        self.assertEqual(self._connection._notification_listener.system_use_notification_received, 'Notification')
        self.assertTrue(mock_send.called)
        mock_send.assert_any_call(fake_data.create_time_request().SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_auth_request_is_sent_when_required_by_server(self, mock_send):
        self._connection._notification_listener = \
            self.TestNotificationListener({'Username': 'Testuser', 'Password': 'testpass'})

        self._connection._handle_hello_message(fake_data.create_valid_hello_response_with_auth_required(b'challenge')
                                               .SerializeToString())
        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 1)
        self.assertEqual(self._connection._notification_listener.credentials_requested_call_count, 1)
        self.assertTrue(mock_send.called)
        mock_send.assert_any_call(
            fake_data.create_password_auth_request(self._connection._challenge,
                                                   self._connection._credentials['Username'],
                                                   self._connection._credentials['Password']).SerializeToString())
        self.assertFalse(self._connection._is_connected)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_connected_state_is_set_when_receiving_auth_response_granted(self, mock_send):
        self.assertFalse(self._connection._is_connected)

        self._connection._handle_auth_response(fake_data.create_auth_response_granted().SerializeToString())

        self.assertTrue(self._connection._is_connected)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_auth_request_is_resent_when_receiving_auth_response_denied(self, mock_send):
        self._connection._challenge = b'challenge'
        self._connection._notification_listener = \
            self.TestNotificationListener({'Username': 'Testuser', 'Password': 'testpass'})

        self._connection._handle_auth_response(fake_data.create_auth_response_denied().SerializeToString())

        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 0)
        self.assertEqual(self._connection._notification_listener.credentials_requested_call_count, 1)
        self.assertTrue(mock_send.called)
        mock_send.assert_any_call(
            fake_data.create_password_auth_request(self._connection._challenge,
                                                   self._connection._credentials['Username'],
                                                   self._connection._credentials['Password']).SerializeToString())
        self.assertFalse(self._connection._is_connected)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_connected_state_is_set_failed_when_user_rejects_credentials_request(self, mock_send):
        self._connection._notification_listener = self.TestNotificationListener()

        self._connection._handle_hello_message(fake_data.create_valid_hello_response_with_auth_required(b'challenge')
                                               .SerializeToString())
        self.assertFalse(mock_send.called)
        self.assertFalse(self._connection._is_connected)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_re_auth_request_is_sent_when_idle_lockout_is_received(self, mock_send):
        self._connection._notification_listener = \
            self.TestNotificationListener({'Username': 'Testuser', 'Password': 'testpass'})

        self._connection._handle_container_message(fake_data.create_auth_response_expired_error(b'challenge').SerializeToString())

        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 0)
        self.assertEqual(self._connection._notification_listener.credentials_requested_call_count, 1)
        self.assertTrue(mock_send.called)
        mock_send.assert_any_call(
            fake_data.create_container_with_password_auth_request(self._connection._challenge,
                                                                  self._connection._credentials['Username'],
                                                                  self._connection._credentials['Password']).SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_pending_request_is_cleared_when_receiving_re_auth_response_granted(self, mock_send):
        self._connection._parse_re_auth_response(fake_data.create_auth_response_granted())

        self.assertEqual(None, self._connection._re_auth_request)

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_re_auth_request_is_resent_when_receiving_re_auth_response_denied(self, mock_send):
        self._connection._challenge = b'challenge'
        self._connection._notification_listener = \
            self.TestNotificationListener({'Username': 'Testuser', 'Password': 'testpass'})

        self._connection._parse_re_auth_response(fake_data.create_auth_response_denied())

        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 0)
        self.assertEqual(self._connection._notification_listener.credentials_requested_call_count, 1)
        self.assertTrue(mock_send.called)
        mock_send.assert_any_call(
            fake_data.create_container_with_password_auth_request(self._connection._challenge,
                                                                  self._connection._credentials['Username'],
                                                                  self._connection._credentials['Password']).SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_connected_state_is_set_failed_when_user_rejects_re_auth_credentials_request(self, mock_send):
        self._connection._notification_listener = self.TestNotificationListener()

        self._connection._handle_container_message(fake_data.create_auth_response_expired_error(b'challenge').SerializeToString())

        self.assertEqual(self._connection._notification_listener.application_acceptance_call_count, 0)
        self.assertEqual(self._connection._notification_listener.credentials_requested_call_count, 1)
        self.assertFalse(mock_send.called)
        self.assertFalse(self._connection._is_connected)
