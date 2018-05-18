from cdp_client import cdp
from cdp_client.tests import fake_data
import pycdp.cdp_pb2 as proto
import unittest
import mock


class ConnectionTester(unittest.TestCase):
    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._connection = None

    def setUp(self):
        self._connection = cdp.Connection("foo", "bar")

    def tearDown(self):
        del self._connection

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_structure_request_when_not_connected(self, mock_send, mock_add):
        self._connection.send_structure_request(1)
        self.assertTrue(mock_add.called)
        mock_send.assert_not_called()

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_structure_request_when_connected(self, mock_send, mock_add):
        self._connection._is_connected = True
        node_id = 1
        self._connection.send_structure_request(node_id)

        data = proto.Container()
        data.message_type = proto.Container.eStructureRequest
        data.structure_request.append(node_id)
        self.assertTrue(mock_add.called)
        mock_send.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.Requests, 'add')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_root_node_structure_request(self, mock_send, mock_add):
        self._connection._is_connected = True
        self._connection.send_structure_request(0)
        data = proto.Container()
        data.message_type = proto.Container.eStructureRequest
        self.assertTrue(mock_add.called)
        mock_send.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value_request(self, mock_send):
        node_id = 1
        self._connection.send_value_request(node_id)

        data = proto.Container()
        data.message_type = proto.Container.eGetterRequest
        value = proto.ValueRequest()
        value.node_id = node_id
        value.fs = 5
        data.getter_request.extend([value])
        mock_send.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value_unrequest(self, mock_send):
        node_id = 1
        self._connection.send_value_unrequest(node_id)

        data = proto.Container()
        data.message_type = proto.Container.eGetterRequest
        value = proto.ValueRequest()
        value.node_id = node_id
        value.fs = 5
        value.stop = True
        data.getter_request.extend([value])
        mock_send.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_sending_value(self, mock_send):
        self._connection.send_value(fake_data.value1)

        data = proto.Container()
        data.message_type = proto.Container.eSetterRequest
        data.setter_request.extend([fake_data.value1])
        mock_send.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.websocket.WebSocketApp, 'run_forever')
    def test_run_until_closed(self, mock_run_forever):
        self._connection.run_until_closed()
        mock_run_forever.assert_called_once_with()

    @mock.patch.object(cdp.Requests, 'clear')
    @mock.patch.object(cdp.websocket.WebSocketApp, 'close')
    def test_run_until_closed(self, mock_close, mock_clear):
        self._connection.close()
        mock_close.assert_called_once_with()
        self.assertTrue(mock_clear.called)

    def test_connected_state_is_set_when_receiving_hello_message_with_correct_version(self):
        data = proto.Hello()
        data.system_name = "foo"
        data.compat_version = 1
        data.incremental_version = 0
        self.assertEquals(self._connection._is_connected, False)
        self._connection._handle_hello_message(None, data.SerializeToString())
        self.assertEquals(self._connection._is_connected, True)

    def test_connected_state_is_unset_when_receiving_hello_message_with_incorrect_version(self):
        data = proto.Hello()
        data.system_name = "foo"
        data.compat_version = 1
        data.incremental_version = 1
        self.assertEquals(self._connection._is_connected, False)
        self._connection._handle_hello_message(None, data.SerializeToString())
        self.assertEquals(self._connection._is_connected, False)

    def test_initialising_node_tree(self):
        self._connection._is_connected = True
        self.assertTrue(self._connection.node_tree().root_node is None)
        self._connection._handle_container_message(None, fake_data.create_system_structure_response().SerializeToString())
        self.assertTrue(self._connection.node_tree().root_node is not None)

    @mock.patch.object(cdp.Node, '_update_structure')
    def test_node_updated_when_node_structure_received(self, mock_update_structure):
        self._connection._is_connected = True
        self._connection._handle_container_message(None, fake_data.create_system_structure_response().SerializeToString())
        response = fake_data.create_app_structure_response()
        self._connection._handle_container_message(None, response.SerializeToString())
        mock_update_structure.assert_called_once_with(response.structure_response[0])

    @mock.patch.object(cdp.Node, '_update_value')
    def test_node_updated_when_node_value_received(self, mock_update_value):
        self._connection._is_connected = True
        self._connection._handle_container_message(None, fake_data.create_system_structure_response().SerializeToString())
        self._connection._handle_container_message(None, fake_data.create_app_structure_response().SerializeToString())
        response = fake_data.create_value_response()
        self._connection._handle_container_message(None, response.SerializeToString())
        mock_update_value.assert_called_once_with(response.getter_response[0])

    @mock.patch.object(cdp.websocket.WebSocketApp, 'send')
    def test_node_structure_requested_when_node_structure_change_received(self, mock_update_structure):
        self._connection._is_connected = True
        self._connection._handle_container_message(None, fake_data.create_system_structure_response().SerializeToString())
        self._connection._handle_container_message(None, fake_data.create_app_structure_response().SerializeToString())
        response = fake_data.create_app_structure_change_response()
        self._connection._handle_container_message(None, response.SerializeToString())
        data = proto.Container()
        data.message_type = proto.Container.eStructureRequest
        data.structure_request.append(response.structure_change_response[0])
        mock_update_structure.assert_called_once_with(data.SerializeToString())

    @mock.patch.object(cdp.Requests, 'clear')
    def test_requests_cleared_when_error_received(self, mock_clear):
        self._connection._handle_container_message(None, fake_data.create_error_response().SerializeToString())
        self.assertTrue(mock_clear.called)
