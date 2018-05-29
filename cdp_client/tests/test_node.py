from promise import Promise
from cdp_client import cdp
from cdp_client.tests import fake_data as data
from copy import copy
import unittest
import mock


class NodeTester(unittest.TestCase):
    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._connection = None

    def setUp(self):
        self._connection = cdp.Connection("foo", "bar", False)
        self._root_node = copy(data.system_node)
        self._root_node.node.extend([data.app1_node, data.app2_node])

    def tearDown(self):
        del self._connection
        del self._root_node

    def test_node_info(self):
        node = cdp.Node(None, self._connection, data.app1_node)
        self.assertEqual(node._id(), data.app1_node.info.node_id)
        self.assertEqual(node.name(), data.app1_node.info.name)
        self.assertEqual(node.type(), cdp.NodeType.APPLICATION)
        self.assertEqual(node.is_leaf(), True)
        self.assertEqual(node.is_read_only(), True)
        self.assertEqual(node.path(), node.name())

        sub_node = cdp.Node(node, self._connection, data.app2_node)
        self.assertEqual(sub_node.path(), node.path() + '.' + sub_node.name())

    def test_value(self):
        node = cdp.Node(None, self._connection, data.value1_node)
        node._update_value(data.value1)
        self.assertEquals(node.last_value(), data.value1.d_value)

    @mock.patch.object(cdp.Connection, 'send_value')
    def test_value_setter(self, mock_send_value):
        node = cdp.Node(None, self._connection, data.value1_node)
        node.set_value(data.value1.d_value, data.value1.timestamp)
        mock_send_value.assert_called_with(data.value1)

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_child_getter_when_child_is_leaf(self, mock_send_structure_request):
        children = []
        node = cdp.Node(None, self._connection, self._root_node)
        node.child(data.app1_node.info.name).then(lambda n: children.append(n))
        mock_send_structure_request.assert_not_called()
        self.assertEqual(children[0]._id(), data.app1_node.info.node_id)
        self.assertEqual(children[0].name(), data.app1_node.info.name)
        self.assertEqual(children[0].type(), cdp.NodeType.APPLICATION)

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_child_getter_when_child_is_not_leaf(self, mock_send_structure_request):
        children = []
        node = cdp.Node(None, self._connection, self._root_node)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(data.app2_node))
        node.child(data.app2_node.info.name).then(lambda n: children.append(n))
        mock_send_structure_request.assert_called_once_with(data.app2_node.info.node_id, node.path() + '.' + data.app2_node.info.name)
        self.assertEqual(children[0]._id(), data.app2_node.info.node_id)
        self.assertEqual(children[0].name(), data.app2_node.info.name)
        self.assertEqual(children[0].type(), cdp.NodeType.APPLICATION)

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_invalid_child_getter(self, mock_send_structure_request):
        errors = []
        node = cdp.Node(None, self._connection, self._root_node)
        node.child("invalid").catch(lambda e: errors.append(e))
        self.assertEqual(len(errors), 1)
        mock_send_structure_request.assert_not_called()

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_children_getter(self, mock_send_structure_request):
        children = []
        node = cdp.Node(None, self._connection, self._root_node)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(data.app2_node))
        node.children().then(lambda n: children.extend(n))
        mock_send_structure_request.assert_called_once_with(data.app2_node.info.node_id, node.path() + '.' + data.app2_node.info.name)
        self.assertEquals(len(children), len(self._root_node.node))

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_children_iterator(self, mock_send_structure_request):
        children = []
        node = cdp.Node(None, self._connection, self._root_node)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(data.app2_node))
        node.for_each_child(lambda n: children.append(n))
        mock_send_structure_request.assert_called_once_with(data.app2_node.info.node_id, node.path() + '.' + data.app2_node.info.name)
        self.assertEquals(len(children), len(self._root_node.node))

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_structure_subscription(self, mock_send_structure_request):
        def on_change(added, removed):
            nodes_added.extend(added)
            nodes_removed.extend(removed)

        old_children = []
        new_children = []
        nodes_added = []
        nodes_removed = []
        node = cdp.Node(None, self._connection, self._root_node)
        node.subscribe_to_structure_changes(on_change)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(data.app2_node))
        node.children().then(lambda n: old_children.extend(n))

        #change the structure - remove and add a node
        node_to_remove = self._root_node.node[0]
        node_to_add = data.app3_node
        self._root_node.node.remove(node_to_remove)
        self._root_node.node.extend([node_to_add])
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(self._root_node))
        node._update()

        #verify
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(node_to_add))
        node.children().then(lambda n: new_children.extend(n))
        self.assertEquals(len(old_children), len(new_children))
        found = False
        for child in new_children:
            self.assertFalse(child.name() == nodes_removed[0])
            if child.name() == nodes_added[0]:
                found = True
        self.assertTrue(found)

    def test_structure_unsubscription(self):
        def on_change(added, removed):
            nodes_added.extend(added)
            nodes_removed.extend(removed)

        nodes_added = []
        nodes_removed = []
        node = cdp.Node(None, self._connection, self._root_node)
        node.subscribe_to_structure_changes(on_change)
        node.unsubscribe_from_structure_changes(on_change)

        # change the structure - remove a node
        node_to_remove = self._root_node.node[0]
        self._root_node.node.remove(node_to_remove)
        node._update_structure(self._root_node)

        # verify
        self.assertEquals(nodes_added, [])
        self.assertEquals(nodes_removed, [])

    @mock.patch.object(cdp.Connection, 'send_value_request')
    def test_value_subscription(self, mock_send_value_request):
        def on_change(value, timestamp):
            actual_values.append(value)
            timestamps.append(timestamp)

        actual_values = []
        timestamps = []
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change)
        mock_send_value_request.assert_called_once_with(node._id())

        expected_values = [data.value1, data.value2]
        for value in expected_values:
            node._update_value(value)

        self.assertEquals(len(actual_values), len(expected_values))
        self.assertEquals(len(timestamps), len(expected_values))
        for index, value in enumerate(expected_values):
            self.assertEquals(actual_values[index], value.d_value)
            self.assertEquals(timestamps[index], value.timestamp)

    @mock.patch.object(cdp.Connection, 'send_value_request')
    @mock.patch.object(cdp.Connection, 'send_value_unrequest')
    def test_value_unsubscription(self, mock_send_value_unrequest, mock_send_value_request):
        def on_change(value):
            values.append(value)

        values = []
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change)
        mock_send_value_request.assert_called_once_with(node._id())
        node.unsubscribe_from_value_changes(on_change)
        mock_send_value_unrequest.assert_called_once_with(node._id())
        node._update_value(data.value1)
        self.assertEquals(len(values), 0)
