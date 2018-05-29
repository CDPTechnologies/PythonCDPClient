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
        self._node_tree = cdp.NodeTree(cdp.Connection("foo", "bar", False))

    def tearDown(self):
        del self._node_tree

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_fetching_root_node_when_root_node_not_existing(self, mock_send_structure_request):
        nodes = []
        system_node = copy(fake_data.system_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([fake_data.value1_node])
        system_node.node.extend([app_node])
        mock_send_structure_request.side_effect = [Promise(lambda resolve, reject: resolve(system_node)),
                                                   Promise(lambda resolve, reject: resolve(app_node))]
        self._node_tree.root_node().then(lambda n: nodes.append(n))
        self.assertEquals(len(nodes), 1)
        self.assertEquals(nodes[0]._id(), app_node.info.node_id)

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_fetching_root_node_when_root_node_existing(self, mock_send_structure_request):
        nodes = []
        root_node = cdp.Node(None, self._node_tree._connection, fake_data.app1_node)
        self._node_tree._root_node = root_node
        self._node_tree.root_node().then(lambda n: nodes.append(n))
        mock_send_structure_request.assert_not_called()
        self.assertEquals(len(nodes), 1)
        self.assertEquals(nodes[0]._id(), root_node._id())

    def test_find_node_by_id(self):
        system_node = copy(fake_data.system_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([fake_data.value1_node])
        system_node.node.extend([app_node])
        root_node = cdp.Node(None, self._node_tree._connection, system_node)
        self._node_tree._root_node = root_node
        node = self._node_tree.find_by_id(fake_data.value1_node.info.node_id)
        self.assertEquals(node._id(), fake_data.value1_node.info.node_id)

    def test_find_node_by_path(self):
        system_node = copy(fake_data.system_node)
        app_node = copy(fake_data.app1_node)
        app_node.node.extend([fake_data.value1_node])
        system_node.node.extend([app_node])
        root_node = cdp.Node(None, self._node_tree._connection, system_node)
        self._node_tree._root_node = root_node
        path = '.'.join([system_node.info.name, app_node.info.name, fake_data.value1_node.info.name])
        node = self._node_tree.find_by_path(path)
        self.assertEquals(node._id(), fake_data.value1_node.info.node_id)
