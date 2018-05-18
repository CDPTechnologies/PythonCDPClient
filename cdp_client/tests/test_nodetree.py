from cdp_client import cdp
from cdp_client.tests import fake_data
from promise import Promise
from copy import copy
import unittest
import mock


class NodeTreeTester(unittest.TestCase):
    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._node_tree = None

    def setUp(self):
        self._node_tree = cdp.NodeTree(cdp.Connection("foo", "bar"))

    def tearDown(self):
        del self._node_tree

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_fetching_root_node_when_root_node_not_existing(self, mock_send_structure_request):
        nodes = []
        root_node = cdp.Node(self._node_tree._connection, fake_data.system_node)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(root_node))
        self._node_tree.fetch_root_node().then(lambda n: nodes.append(n))
        mock_send_structure_request.assert_called_once_with(0)
        self.assertEquals(len(nodes), 1)
        self.assertEquals(nodes[0].id(), root_node.id())

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_fetching_root_node_when_root_node_existing(self, mock_send_structure_request):
        nodes = []
        root_node = cdp.Node(self._node_tree._connection, fake_data.system_node)
        self._node_tree.root_node = root_node
        self._node_tree.fetch_root_node().then(lambda n: nodes.append(n))
        mock_send_structure_request.assert_not_called()
        self.assertEquals(len(nodes), 1)
        self.assertEquals(nodes[0].id(), root_node.id())

    def test_find_node(self):
        system_node = copy(fake_data.system_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([fake_data.value1_node])
        system_node.node.extend([app_node])
        root_node = cdp.Node(self._node_tree._connection, system_node)
        self._node_tree.root_node = root_node
        node = self._node_tree.find(fake_data.value1_node.info.node_id)
        self.assertEquals(node.id(), fake_data.value1_node.info.node_id)
