from cdp_client import cdp
from cdp_client.tests import fake_data
from promise import Promise
from copy import copy
import unittest
import mock


class ClientTester(unittest.TestCase):
    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._client = None

    def setUp(self):
        self._client = cdp.Client("foo")

    def tearDown(self):
        del self._client

    @mock.patch.object(cdp.Connection, 'node_tree')
    def _test_root_getter(self, mock_node_tree):
        nodes = []
        node_tree = cdp.NodeTree(self._client._connection)
        node_tree.root_node = cdp.Node(self._client._connection, fake_data.system_node)
        mock_node_tree.return_value = node_tree
        self._client.root_node().then(lambda node: nodes.append(node))
        mock_node_tree.assert_called_once_with()
        self.assertEquals(nodes[0].id(), fake_data.system_node.info.node_id)

    @mock.patch.object(cdp.Connection, 'node_tree')
    @mock.patch.object(cdp.Node, 'child')
    def test_find_node(self, mock_child, mock_node_tree):
        nodes = []
        system_node = copy(fake_data.system_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([fake_data.value1_node])
        system_node.node.extend([app_node])
        mock_node_tree.return_value = cdp.NodeTree(self._client._connection)
        mock_node_tree.return_value.root_node = cdp.Node(self._client._connection, system_node)
        mock_child.side_effect = [Promise(lambda resolve, reject: resolve(cdp.Node(self._client._connection, app_node))),
                                  Promise(lambda resolve, reject: resolve(cdp.Node(self._client._connection, fake_data.value1_node)))]
        routing = '.'.join([app_node.info.name, fake_data.value1_node.info.name])
        self._client.find_node(routing).then(lambda node: nodes.append(node))
        self.assertEquals(nodes[0].id(), fake_data.value1_node.info.node_id)

    @mock.patch.object(cdp.Connection, 'run_event_loop')
    def test_run_until_disconnected(self, mock_run_event_loop):
        self._client.run_event_loop()
        mock_run_event_loop.assert_called_once_with()

    @mock.patch.object(cdp.Connection, 'close')
    def test_disconnect(self, mock_close):
        self._client.disconnect()
        mock_close.assert_called_once_with()