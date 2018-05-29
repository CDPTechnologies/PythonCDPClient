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

    @mock.patch.object(cdp.NodeTree, 'root_node')
    def test_root_getter(self, mock_root_node):
        nodes = []
        mock_root_node.return_value = Promise(lambda resolve, reject: resolve(cdp.Node(None, self._client._connection, fake_data.system_node)))
        self._client.root_node().then(lambda node: nodes.append(node))
        mock_root_node.assert_called_once_with()
        self.assertEquals(nodes[0]._id(), fake_data.system_node.info.node_id)

    @mock.patch.object(cdp.NodeTree, 'root_node')
    @mock.patch.object(cdp.Node, 'child')
    def test_find_node(self, mock_child, mock_root_node):
        nodes = []
        comp_node = copy(fake_data.comp1_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([comp_node])
        comp_node.node.extend([fake_data.value1_node])
        mock_root_node.return_value = Promise(lambda resolve, reject: resolve(cdp.Node(None, self._client._connection, app_node)))
        mock_child.side_effect = [Promise(lambda resolve, reject: resolve(cdp.Node(None, self._client._connection, comp_node))),
                                  Promise(lambda resolve, reject: resolve(cdp.Node(None, self._client._connection, fake_data.value1_node)))]
        path = '.'.join([app_node.info.name, comp_node.info.name, fake_data.value1_node.info.name])
        self._client.find_node(path).then(lambda node: nodes.append(node))
        self.assertEquals(nodes[0]._id(), fake_data.value1_node.info.node_id)

    @mock.patch.object(cdp.Connection, 'run_event_loop')
    def test_run_event_loop(self, mock_run_event_loop):
        self._client.run_event_loop()
        mock_run_event_loop.assert_called_once_with()

    @mock.patch.object(cdp.Connection, 'close')
    def test_disconnect(self, mock_close):
        self._client.disconnect()
        mock_close.assert_called_once_with()
