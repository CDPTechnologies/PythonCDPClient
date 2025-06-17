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
        self.assertEqual(node.last_value(), data.value1.d_value)

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
        self.assertEqual(len(children), len(self._root_node.node))

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    def test_children_iterator(self, mock_send_structure_request):
        children = []
        node = cdp.Node(None, self._connection, self._root_node)
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(data.app2_node))
        node.for_each_child(lambda n: children.append(n))
        mock_send_structure_request.assert_called_once_with(data.app2_node.info.node_id, node.path() + '.' + data.app2_node.info.name)
        self.assertEqual(len(children), len(self._root_node.node))

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

        # change the structure - remove and add a node
        node_to_remove = self._root_node.node[0]
        node_to_add = data.app3_node
        self._root_node.node.remove(node_to_remove)
        self._root_node.node.extend([node_to_add])
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(self._root_node))
        node._update()

        # verify
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(node_to_add))
        node.children().then(lambda n: new_children.extend(n))
        self.assertEqual(len(old_children), len(new_children))
        found = False
        for child in new_children:
            self.assertFalse(child.name() == nodes_removed[0].name())
            if child.name() == nodes_added[0].name():
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
        self.assertEqual(nodes_added, [])
        self.assertEqual(nodes_removed, [])

    @mock.patch.object(cdp.Connection, 'send_value_request')
    def test_value_subscription(self, mock_send_value_request):
        def on_change(value, timestamp):
            actual_values.append(value)
            timestamps.append(timestamp)
        actual_values = []
        timestamps = []
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change, 10, 5)
        mock_send_value_request.assert_called_once_with(node._id(), 10, 5)

        expected_values = [data.value1, data.value2]
        for value in expected_values:
            node._update_value(value)

        self.assertEqual(len(actual_values), len(expected_values))
        self.assertEqual(len(timestamps), len(expected_values))
        for index, value in enumerate(expected_values):
            self.assertEqual(actual_values[index], value.d_value)
            self.assertEqual(timestamps[index], value.timestamp)
    
    @mock.patch.object(cdp.Connection, 'send_value_request')
    def test_value_subscription_max_fs(self, mock_send_value_request):
        def on_change1():
            pass
        def on_change2():
            pass
        def on_change3():
            pass
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change1, 3, 1)
        mock_send_value_request.assert_called_once_with(node._id(), 3, 1)
        mock_send_value_request.reset_mock()
        node.subscribe_to_value_changes(on_change2, 10, 6)
        mock_send_value_request.assert_called_once_with(node._id(), 10, 6)
        mock_send_value_request.reset_mock()
        node.subscribe_to_value_changes(on_change3, 1, 3)
        mock_send_value_request.assert_called_once_with(node._id(), 10, 6)

    @mock.patch.object(cdp.Connection, 'send_structure_request')
    @mock.patch.object(cdp.Connection, 'send_value_request')
    def test_value_subscription_max_fs_on_update(self, mock_send_value_request, mock_send_structure_request):
        def on_change1():
            pass
        def on_change2():
            pass
        def on_change3():
            pass
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change1, 3, 1)
        node.subscribe_to_value_changes(on_change2, 10, 6)
        node.subscribe_to_value_changes(on_change3, 1, 6)
        mock_send_value_request.reset_mock()
        mock_send_structure_request.return_value = Promise(lambda resolve, reject: resolve(self._root_node))
        node._update()
        mock_send_value_request.assert_called_once_with(node._id(), 10, 6)

    @mock.patch.object(cdp.Connection, 'send_value_request')
    @mock.patch.object(cdp.Connection, 'send_value_unrequest')
    def test_value_unsubscription(self, mock_send_value_unrequest, mock_send_value_request):
        def on_change(value):
            values.append(value)

        values = []
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change)
        mock_send_value_request.assert_called_once_with(node._id(), 5, 0)
        node.unsubscribe_from_value_changes(on_change)
        mock_send_value_unrequest.assert_called_once_with(node._id())
        node._update_value(data.value1)
        self.assertEqual(len(values), 0)

    @mock.patch.object(cdp.Connection, 'send_value_request')
    def test_value_unsubscription_max_fs(self, mock_send_value_request):
        def on_change1():
            pass
        def on_change2():
            pass
        def on_change3():
            pass
        node = cdp.Node(None, self._connection, data.value1_node)
        node.subscribe_to_value_changes(on_change1, 5, 1)
        node.subscribe_to_value_changes(on_change2, 1, 3)
        node.subscribe_to_value_changes(on_change3, 10, 6)
        mock_send_value_request.reset_mock()
        node.unsubscribe_from_value_changes(on_change3)
        mock_send_value_request.assert_called_once_with(node._id(), 5, 3)

    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_event_subscription(self, mock_send_event_request):
        def on_event(event_info):
            received_events.append(event_info)
        
        received_events = []
        node = cdp.Node(None, self._connection, data.app1_node)
        node.subscribe_to_events(on_event)
        mock_send_event_request.assert_called_once_with(node._id(), None)
        
        # Simulate receiving events
        node._update_event(data.event_info1)
        node._update_event(data.event_info2)
        
        self.assertEqual(len(received_events), 2)
        self.assertEqual(received_events[0].id, data.event_info1.id)
        self.assertEqual(received_events[0].sender, data.event_info1.sender)
        self.assertEqual(received_events[0].code, data.event_info1.code)
        self.assertEqual(received_events[1].id, data.event_info2.id)

    @mock.patch.object(cdp.Connection, 'send_event_unrequest')
    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_event_unsubscription(self, mock_send_event_request, mock_send_event_unrequest):
        def on_event(event_info):
            received_events.append(event_info)
        
        received_events = []
        node = cdp.Node(None, self._connection, data.app1_node)
        node.subscribe_to_events(on_event)
        
        node.unsubscribe_from_events(on_event)
        mock_send_event_unrequest.assert_called_once_with(node._id())
        
        # Events should not be received after unsubscription
        node._update_event(data.event_info1)
        self.assertEqual(len(received_events), 0)

    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_multiple_event_subscriptions(self, mock_send_event_request):
        def on_event1(event_info):
            events1.append(event_info)
        def on_event2(event_info):
            events2.append(event_info)
        
        events1 = []
        events2 = []
        node = cdp.Node(None, self._connection, data.app1_node)
        
        # Subscribe multiple callbacks
        node.subscribe_to_events(on_event1)
        node.subscribe_to_events(on_event2)
        
        # Send event - both should receive it
        node._update_event(data.event_info1)
        
        self.assertEqual(len(events1), 1)
        self.assertEqual(len(events2), 1)
        self.assertEqual(events1[0].id, data.event_info1.id)
        self.assertEqual(events2[0].id, data.event_info1.id)

    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_event_data_parsing(self, mock_send_event_request):
        def on_event(event_info):
            received_events.append(event_info)
        
        received_events = []
        node = cdp.Node(None, self._connection, data.app1_node)
        node.subscribe_to_events(on_event)
        
        # Send event with data
        node._update_event(data.event_info1)
        
        self.assertEqual(len(received_events), 1)
        event = received_events[0]
        self.assertEqual(len(event.data), 2)
        self.assertEqual(event.data[0].name, "temperature")
        self.assertEqual(event.data[0].value, "25.5")
        self.assertEqual(event.data[1].name, "status")
        self.assertEqual(event.data[1].value, "OK")

    @mock.patch.object(cdp.Connection, 'send_event_unrequest')
    def test_event_unsubscribe_nonexistent_callback(self, mock_send_event_unrequest):
        def on_event(event_info):
            pass
        def unsubscribed_callback(event_info):
            pass
        
        node = cdp.Node(None, self._connection, data.app1_node)
        
        # Try to unsubscribe a callback that was never subscribed
        # Should not cause any errors or send unrequest
        node.unsubscribe_from_events(unsubscribed_callback)
        mock_send_event_unrequest.assert_not_called()

    @mock.patch.object(cdp.Connection, 'send_event_unrequest') 
    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_event_partial_unsubscription(self, mock_send_event_request, mock_send_event_unrequest):
        def on_event1(event_info):
            pass
        def on_event2(event_info):
            pass
        
        node = cdp.Node(None, self._connection, data.app1_node)
        
        # Subscribe two callbacks
        node.subscribe_to_events(on_event1)
        node.subscribe_to_events(on_event2)
        
        # Unsubscribe only one - should NOT send unrequest yet
        node.unsubscribe_from_events(on_event1)
        mock_send_event_unrequest.assert_not_called()
        
        # Unsubscribe the last one - should send unrequest
        node.unsubscribe_from_events(on_event2)
        mock_send_event_unrequest.assert_called_once_with(node._id())

    @mock.patch.object(cdp.Connection, 'send_event_request')
    def test_event_subscription_with_starting_from(self, mock_send_event_request):
        def on_event(event_info):
            pass
        
        node = cdp.Node(None, self._connection, data.app1_node)
        starting_timestamp = 1234567890
        
        # Subscribe with starting_from parameter
        node.subscribe_to_events(on_event, starting_timestamp)
        mock_send_event_request.assert_called_once_with(node._id(), starting_timestamp)
