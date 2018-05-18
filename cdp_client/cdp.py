from promise import Promise
import cdp_pb2 as proto
import websocket
import logging


def enum(**enums):
    return type('Enum', (), enums)

NodeType = enum(
    UNDEFINED=-1,
    SYSTEM=0,
    APPLICATION=1,
    COMPONENT=2,
    OBJECT=3,
    MESSAGE=4,
    BASE_OBJECT=5,
    PROPERTY=6,
    SETTING=7,
    ENUM=8,
    OPERATOR=9,
    NODE=10,
    USER_TYPE=100)


class ConnectionError(Exception):
    pass


class CommunicationError(Exception):
    pass


class InvalidRequestError(Exception):
    pass


class NotFoundError(Exception):
    pass


class UnknownError(Exception):
    pass


class Client:
    def __init__(self, host, port=7689):
        self._connection = Connection(host, port)

    def run_event_loop(self):
        self._connection.run_event_loop()

    def disconnect(self):
        self._connection.close()

    def root_node(self):
        return self._connection.node_tree().fetch_root_node()

    def find_node(self, path):
        def scan_node(node):
            tokens.pop(0)
            if not tokens:
                return Promise(lambda resolve, reject: resolve(node))
            return node.child(tokens[0]).then(scan_node)

        tokens = path.split('.')
        tokens.insert(0, 'root_placeholder')
        return self.root_node().then(scan_node)


class Node:
    def __init__(self, connection, structure):
        self._connection = connection
        self._structure = structure
        self._children = []
        self._structure_subscriptions = []
        self._value_subscriptions = []
        self._value = proto.VariantValue()
        for child in self._structure.node:
            self._children.append(Node(connection, child))

    def last_value(self):
        return self._value

    def set_value(self, value, timestamp=0):
        variant = self._value_to_variant(self._structure.info.value_type, value)
        variant.node_id = self.id()
        variant.timestamp = timestamp
        self._connection.send_value(variant)

    def id(self):
        return self._structure.info.node_id

    def name(self):
        return self._structure.info.name

    def type(self):
        return self._translate_type(self._structure.info.node_type)

    def is_read_only(self):
        return self._structure.info.flags & proto.Info.eValueIsReadOnly != 0

    def is_leaf(self):
        return self._structure.info.flags & proto.Info.eNodeIsLeaf != 0

    def child(self, name):
        for child in self._children:
            if child.name() == name:
                if child.is_leaf():
                    return Promise(lambda resolve, reject: resolve(child))
                return self._connection.send_structure_request(child.id())
        return Promise(lambda resolve, reject: reject(NotFoundError("Could not find any children with name '" + name + "'")))

    def children(self):
        promises = []
        for child in self._children:
            promises.append(self.child(child.name()))
        return Promise.all(promises)

    def for_each_child(self, callback):
        for child in self._children:
            self.child(child.name()).done(callback)

    def subscribe_to_structure_changes(self, callback):
        self._structure_subscriptions.append(callback)

    def subscribe_to_value_changes(self, callback):
        self._value_subscriptions.append(callback)
        self._connection.send_value_request(self.id())

    def unsubscribe_from_structure_changes(self, callback):
        self._structure_subscriptions.remove(callback)

    def unsubscribe_from_value_changes(self, callback):
        self._value_subscriptions.remove(callback)
        if not self._value_subscriptions:
            self._connection.send_value_unrequest(self.id())

    def _update_structure(self, structure):
        self._structure = structure
        new_children = list(self._structure.node)
        lost_children = list(self._children)
        removed_children = []
        added_children = []

        def diff():
            for n in self._structure.node:
                for existing_child in self._children:
                    if n.info.node_id == existing_child.id():
                        new_children.remove(n)
                        lost_children.remove(existing_child)

        diff()
        for child in lost_children:
            removed_children.append(child.name())
            self._children.remove(child)
        for child in new_children:
            node = Node(self._connection, child)
            self._children.append(node)
            added_children.append(node.name())

        if added_children or removed_children:
            for callback in self._structure_subscriptions:
                callback(added_children, removed_children)

    def _update_value(self, variant):
        self._value = self._value_from_variant(self._structure.info.value_type, variant)
        for callback in self._value_subscriptions:
            callback(self._value, variant.timestamp)

    @staticmethod
    def _translate_type(node_type):
        if node_type == proto.CDP_SYSTEM:
            return NodeType.SYSTEM
        elif node_type == proto.CDP_APPLICATION:
            return NodeType.APPLICATION
        elif node_type == proto.CDP_COMPONENT:
            return NodeType.COMPONENT
        elif node_type == proto.CDP_OBJECT:
            return NodeType.OBJECT
        elif node_type == proto.CDP_MESSAGE:
            return NodeType.MESSAGE
        elif node_type == proto.CDP_BASE_OBJECT:
            return NodeType.BASE_OBJECT
        elif node_type == proto.CDP_PROPERTY:
            return NodeType.PROPERTY
        elif node_type == proto.CDP_SETTING:
            return NodeType.SETTING
        elif node_type == proto.CDP_ENUM:
            return NodeType.ENUM
        elif node_type == proto.CDP_OPERATOR:
            return NodeType.OPERATOR
        elif node_type == proto.CDP_NODE:
            return NodeType.NODE
        elif node_type == proto.CDP_USER_TYPE:
            return NodeType.USER_TYPE
        else:
            return NodeType.UNDEFINED

    @staticmethod
    def _value_from_variant(type, variant):
        if type == proto.eDOUBLE:
            return variant.d_value
        elif type == proto.eUINT64:
            return variant.f_value
        elif type == proto.eINT64:
            return variant.ui64_value
        elif type == proto.eFLOAT:
            return variant.i64_value
        elif type == proto.eUINT:
            return variant.ui_value
        elif type == proto.eINT:
            return variant.i_value
        elif type == proto.eUSHORT:
            return variant.us_value
        elif type == proto.eSHORT:
            return variant.s_value
        elif type == proto.eUCHAR:
            return variant.uc_value
        elif type == proto.eCHAR:
            return variant.c_value
        elif type == proto.eBOOL:
            return variant.b_value
        elif type == proto.eSTRING:
            return variant.str_value
        else:
            return None

    @staticmethod
    def _value_to_variant(type, value):
        variant = proto.VariantValue()
        if type == proto.eDOUBLE:
            variant.d_value = value
        elif type == proto.eUINT64:
            variant.f_value = value
        elif type == proto.eINT64:
            variant.ui64_value = value
        elif type == proto.eFLOAT:
            variant.i64_value = value
        elif type == proto.eUINT:
            variant.ui_value = value
        elif type == proto.eINT:
            variant.i_value = value
        elif type == proto.eUSHORT:
            variant.us_value = value
        elif type == proto.eSHORT:
            variant.s_value = value
        elif type == proto.eUCHAR:
            variant.uc_value = value
        elif type == proto.eCHAR:
            variant.c_value = value
        elif type == proto.eBOOL:
            variant.b_value = value
        elif type == proto.eSTRING:
            variant.str_value = str(value)
        return variant


class Connection:
    def __init__(self, host, port):
        self._node_tree = NodeTree(self)
        self._structure_requests = Requests()
        self._value_requests = Requests()
        self._is_connected = False
        self._ws = websocket.WebSocketApp("ws://" + host + ":" + str(port),
                                          on_message=self._handle_hello_message,
                                          on_error=self._on_error,
                                          on_close=self._on_close,
                                          on_open=self._on_open)

    def node_tree(self):
        return self._node_tree

    def send_structure_request(self, node_id):
        def send(resolve, reject):
            self._structure_requests.add(node_id, resolve, reject)
            if self._is_connected:
                self._compose_and_send_structure_request(node_id)
        return Promise(send)

    def send_value_request(self, node_id):
        self._compose_and_send_value_request(node_id)

    def send_value_unrequest(self, node_id):
        self._compose_and_send_value_request(node_id, True)

    def send_value(self, variant):
        self._compose_and_send_value(variant)

    def run_event_loop(self):
        self._ws.run_forever()

    def close(self):
        self._on_close(self._ws)
        self._ws.close()

    def _on_error(self, ws, error):
        self._cleanup_queued_requests(ConnectionError(error))

    def _on_close(self, ws):
        self._cleanup_queued_requests(ConnectionError("Connection was closed"))

    def _on_open(self, ws):
        pass

    def _handle_hello_message(self, ws, message):
        if self._parse_hello_message(message):
            self._is_connected = True
            self._ws.on_message = self._handle_container_message
            self._send_queued_requests()
        else:
            self._cleanup_queued_requests(CommunicationError("Protocol mismatch"))

    def _handle_container_message(self, ws, message):
        data = proto.Container()
        data.ParseFromString(message)
        if data.message_type == proto.Container.eStructureResponse:
            self._parse_structure_response(data.structure_response)
        elif data.message_type == proto.Container.eGetterResponse:
            self._parse_getter_response(data.getter_response)
        elif data.message_type == proto.Container.eStructureChangeResponse:
            self._parse_structure_change_response(data.structure_change_response)
        elif data.message_type == proto.Container.eCurrentTimeResponse:
            self._parse_current_time_response(data.structure_response)
        elif data.message_type == proto.Container.eRemoteError:
            self._parse_error_response(data.error)
        else:
            logging.info("Unsupported message type received")

    def _parse_getter_response(self, response):
        for variant in response:
            node = self._node_tree.find(variant.node_id)
            node._update_value(variant)

    def _parse_structure_change_response(self, response):
        for node_id in response:
            self.send_structure_request(node_id)

    def _parse_current_time_response(self, response):
        pass

    def _parse_error_response(self, error):
        if error.code == proto.eINVALID_REQUEST:
            self._cleanup_queued_requests(InvalidRequestError(error.text))
        elif error.code == proto.eUNSUPPORTED_CONTAINER_TYPE:
            self._cleanup_queued_requests(CommunicationError(error.text))

    def _parse_hello_message(self, message):
        data = proto.Hello()
        data.ParseFromString(message)
        if data.compat_version == 1 and data.incremental_version == 0:
            return True
        logging.info("Unsupported protocol version " + str(data.compat_version) + '.' + str(data.incremental_version))
        return False

    def _parse_structure_response(self, response):
        for structure in response:
            node = None
            if self._node_tree.root_node is None and structure.info.node_id == 0:
                self._node_tree.root_node = Node(self, structure)
                node = self._node_tree.root_node
            else:
                node = self._node_tree.find(structure.info.node_id)
                node._update_structure(structure)

            request = self._structure_requests.find(structure.info.node_id)
            if request is not None:
                self._structure_requests.remove(structure.info.node_id)
                for request in request['resolve_callbacks']:
                    request(node)

    def _send_queued_requests(self):
        for request in self._structure_requests.get():
            self._compose_and_send_structure_request(request['node_id'])

    def _cleanup_queued_requests(self, error):
        self._structure_requests.clear(error)

    def _compose_and_send_structure_request(self, node_id):
        data = proto.Container()
        data.message_type = proto.Container.eStructureRequest
        if node_id is not 0:
            data.structure_request.append(node_id)
        self._ws.send(data.SerializeToString())

    def _compose_and_send_value_request(self, node_id, stop=False):
        data = proto.Container()
        data.message_type = proto.Container.eGetterRequest
        value = proto.ValueRequest()
        value.node_id = node_id
        value.fs = 5
        if stop:
            value.stop = stop
        data.getter_request.extend([value])
        self._ws.send(data.SerializeToString())

    def _compose_and_send_value(self, variant):
        data = proto.Container()
        data.message_type = proto.Container.eSetterRequest
        data.setter_request.extend([variant])
        self._ws.send(data.SerializeToString())


class NodeTree:
    def __init__(self, connection):
        self._connection = connection
        self.root_node = None

    def fetch_root_node(self):
        if self.root_node is None:
            return self._connection.send_structure_request(0)
        return Promise(lambda resolve, reject: resolve(self.root_node))

    def find(self, node_id):
        def find_node(node):
            if node.id() == node_id:
                return node
            for child in node._children:
                node = find_node(child)
                if node is not None:
                    return node
            return None

        if self.root_node is None:
            return None
        return find_node(self.root_node)


class Requests:
    def __init__(self):
        self._requests = []

    def get(self):
        return self._requests

    def add(self, node_id, resolve, reject):
        request = self.find(node_id)
        if request is None:
            request = {'node_id': node_id, 'resolve_callbacks': [resolve], 'reject_callbacks': [reject]}
            self._requests.append(request)
        else:
            if resolve not in request['resolve_callbacks']:
                request['resolve_callbacks'].append(resolve)
            if reject not in request['reject_callbacks']:
                request['reject_callbacks'].append(reject)

    def find(self, node_id):
        for r in self._requests:
            if r['node_id'] == node_id:
                return r
        return None

    def remove(self, node_id):
        request = self.find(node_id)
        self._requests.remove(request)

    def clear(self, error=UnknownError('Something has went wrong')):
        for request in self._requests:
            for r in request['reject_callbacks']:
                r(error)
        del self._requests[:]
