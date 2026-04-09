from promise import Promise
from time import sleep
from collections import namedtuple
from hashlib import sha256
import cdp_client.cdp_pb2 as proto
import websocket
import logging
import threading
import time

nanoseconds_in_second = 1000000000.0

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


SiblingEvent = enum(
    CONNECTED=1,    # sibling app reachable for the first time in this session
    DISCONNECTED=2, # sibling app went offline (transport closed or proxy handshake timed out)
    RECONNECTED=3,  # sibling app came back after a previous DISCONNECTED
)


AuthResultCode = enum(
    CREDENTIALS_REQUIRED=0,
    # OK results:
    GRANTED=1, # is also set when no authentication required
    GRANTED_PASSWORD_WILL_EXPIRE_SOON = 2, # user should be notified about coming soon password expiry
                                           # with suggestion to set a new password ASAP
    # negative results:
    NEW_PASSWORD_REQUIRED = 10, # password was OK but is expired, so new AuthRequest with additional
                                # response with new password hash is required, and new password
                                # complexity rules should be read from additionalCredentials[CredentialNewpassword].parameters
    INVALID_CHALLENGE_RESPONSE = 11,
    ADDITIONAL_RESPONSE_REQUIRED = 12,
    TEMPORARILY_BLOCKED = 13,
    REAUTHENTICATION_REQUIRED = 14 # server requires re-authentication (e.g.because of being idle),
                                   # implementation should prompt the user for re-authentication
                                   # (must not silently send cached credentials)
)

class UserAuthResult:
    def __init__(self, code=AuthResultCode.CREDENTIALS_REQUIRED, text='', additional_credentials=None):
        self._code = code
        self._text = text
        self._additional_credentials = additional_credentials

    def code(self):
        return self._code

    def text(self):
        return self._text

    def additional_credentials(self):
        return self._additional_credentials


class AuthRequest(Promise):
    def __init__(self, system_name='', application_name='', host='', port='', cdp_version='',
                 system_use_notification=None, user_auth_result=UserAuthResult()):
        self._system_name = system_name
        self._application_name = application_name
        self._host = host
        self._port = port
        self._cdp_version = cdp_version
        self._system_use_notification = system_use_notification
        self._user_auth_result = user_auth_result

    def system_name(self):
        return self._system_name

    def application_name(self):
        return self._application_name

    def host(self):
        return self._host

    def port(self):
        return self._port

    def cdp_version(self):
        return self._cdp_version

    def user_auth_result(self):
        return self._user_auth_result

    def system_use_notification(self):
        return self._system_use_notification

    def accept(self, data=dict()):
        self.do_resolve(data)

    def reject(self):
        self.do_reject(UnknownError('Authentication rejected'))


class NotificationListener:
    def application_acceptance_requested(self, request=AuthRequest()):
        request.accept()

    def credentials_requested(self, request=AuthRequest()):
        raise NotImplementedError("NotificationListener credentials_requested() not implemented!")


class Client:
    def __init__(self, host='127.0.0.1', port=7689, auto_reconnect=True, notification_listener=NotificationListener(),
                 encryption_parameters=dict()):
        self._connection = Connection(host, port, auto_reconnect, notification_listener, encryption_parameters)

    def run_event_loop(self):
        self._connection.run_event_loop()

    def disconnect(self):
        self._connection.close()

    def root_node(self):
        return self._connection.node_tree().root_node()

    def find_node(self, path):
        def scan_node(node):
            tokens.pop(0)
            if not tokens:
                return Promise(lambda resolve, reject: resolve(node))
            return node.child(tokens[0]).then(scan_node)

        tokens = path.split('.')
        def start_scan(root):
            if root.name() == tokens[0]:
                return scan_node(root)
            # Check sibling connections for the target app
            for sibling in list(self._connection._sibling_connections.values()):
                sibling_root = sibling._node_tree._root_node
                if sibling_root is not None and sibling_root.name() == tokens[0]:
                    return scan_node(sibling_root)
            return Promise(lambda resolve, reject: reject(
                NotFoundError("Application '" + tokens[0] + "' not found")))

        return self.root_node().then(start_scan)

    def subscribe_to_sibling_changes(self, callback):
        self._connection.subscribe_to_sibling_changes(callback)

    def unsubscribe_from_sibling_changes(self, callback):
        self._connection.unsubscribe_from_sibling_changes(callback)


class Node:
    def __init__(self, parent, connection, structure):
        self._connection = connection
        self._structure = structure
        self._children = []
        self._structure_subscriptions = []
        self._value_subscriptions = []
        self._event_subscriptions = []
        self._value = proto.VariantValue()
        self._parent = parent
        for child in self._structure.node:
            self._children.append(Node(self, connection, child))

    def last_value(self):
        return self._value

    def set_value(self, value, timestamp=0):
        variant = self._value_to_variant(self._structure.info.value_type, value)
        variant.node_id = self._id()
        variant.timestamp = timestamp
        self._connection.send_value(variant)

    def name(self):
        return self._structure.info.name

    def path(self):
        return self.name() if self._parent is None else self._parent.path() + '.' + self.name()

    def parent(self):
        return self._parent

    def type(self):
        return self._translate_type(self._structure.info.node_type)

    def class_name(self):
        return self._structure.info.type_name

    def is_read_only(self):
        return self._structure.info.flags & proto.Info.eValueIsReadOnly != 0

    def is_leaf(self):
        return self._structure.info.flags & proto.Info.eNodeIsLeaf != 0

    def child(self, name):
        def update_node(node, structure):
            node._update_structure(structure)
            return Promise(lambda resolve, reject: resolve(node))

        for child in self._children:
            if child.name() == name:
                if child.is_leaf():
                    return Promise(lambda resolve, reject: resolve(child))
                return self._connection.send_structure_request(child._id(), child.path()).then(lambda structure: update_node(child, structure))
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

    def subscribe_to_value_changes(self, callback, fs=5, sample_rate=0):
        self._value_subscriptions.append((callback, fs, sample_rate))
        self._send_value_request()

    def unsubscribe_from_structure_changes(self, callback):
        self._structure_subscriptions.remove(callback)

    def unsubscribe_from_value_changes(self, callback):
        self._value_subscriptions = [i for i in self._value_subscriptions if i[0] != callback]
        if self._value_subscriptions:
            self._send_value_request()
        else:
            self._connection.send_value_unrequest(self._id())

    def subscribe_to_events(self, callback, starting_from=None):
        """Starts listening to events from this node and its children.

        Args:
            callback: Function(event_info) to call when events are received
            starting_from: Optional timestamp to start receiving events from (nanoseconds since Epoch)
        """
        self._event_subscriptions.append(callback)
        self._connection.send_event_request(self._id(), starting_from)

    def unsubscribe_from_events(self, callback):
        """Stops listening to previously subscribed events.

        Args:
            callback: Function(event_info) that was previously subscribed
        """
        if callback in self._event_subscriptions:
            self._event_subscriptions.remove(callback)
            if not self._event_subscriptions:
                self._connection.send_event_unrequest(self._id())

    def _id(self):
        return self._structure.info.node_id

    def _update(self):
        def update_structure(structure):
            self._update_structure(structure)
            return Promise(lambda resolve, reject: resolve(self))

        def fetch_structure():
            return self._connection.send_structure_request(self._id(), self.path())

        def fetch_value(node):
            if self._value_subscriptions:
                self._send_value_request()
            return Promise(lambda resolve, reject: resolve(node))

        return fetch_structure().then(update_structure).then(fetch_value)

    def _send_value_request(self):
        max_fs = max(self._value_subscriptions, key=lambda e: e[1])[1]
        max_sample_rate = max(self._value_subscriptions, key=lambda e: e[2])[2]
        #by studio api protocol 0 is the highest sample rate (all samples), so override maxSampleRate if 0 is found
        for s in self._value_subscriptions:
            if s[2] == 0:
                max_sample_rate = 0
                break
        self._connection.send_value_request(self._id(), max_fs, max_sample_rate)

    def _update_structure(self, structure):
        self._structure = structure
        new_children = list(self._structure.node)
        lost_children = list(self._children)
        removed_children = []
        added_children = []

        def update_matching_children():
            # Match by name (not node_id) so user-held Node references survive
            # server restarts that reassign node_ids. After a sibling rebind
            # or auto-reconnect to a freshly started server, existing children
            # may have stale ids; matching by name lets us update their
            # _structure in-place to the fresh server-assigned id without
            # orphaning user-held references.
            for node in self._structure.node:
                for child in self._children:
                    if node.info.name == child.name():
                        child._structure = node

        def diff_children():
            for n in self._structure.node:
                for existing_child in self._children:
                    if n.info.node_id == existing_child._id():
                        if n in new_children:
                            new_children.remove(n)
                        if existing_child in lost_children:
                            lost_children.remove(existing_child)

        def report_children_diff():
            for child in lost_children:
                removed_children.append(child)
                if child in self._children:
                    self._children.remove(child)
            for child in new_children:
                node = Node(self, self._connection, child)
                self._children.append(node)
                added_children.append(node)

            if added_children or removed_children:
                for callback in self._structure_subscriptions:
                    callback(added_children, removed_children)

        update_matching_children()  # update children so that children structure response can lookup nodes by correct node id
        diff_children()
        report_children_diff()

    def _update_value(self, variant):
        self._value = self._value_from_variant(self._structure.info.value_type, variant)
        for callback, fs, sample_rate in self._value_subscriptions:
            callback(self._value, variant.timestamp + self._connection.server_time_difference() * nanoseconds_in_second)

    def _update_event(self, event_info):
        for callback in self._event_subscriptions:
            callback(event_info)

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
            variant.f_value = int(value)
        elif type == proto.eINT64:
            variant.ui64_value = int(value)
        elif type == proto.eFLOAT:
            variant.i64_value = value
        elif type == proto.eUINT:
            variant.ui_value = int(value)
        elif type == proto.eINT:
            variant.i_value = int(value)
        elif type == proto.eUSHORT:
            variant.us_value = int(value)
        elif type == proto.eSHORT:
            variant.s_value = int(value)
        elif type == proto.eUCHAR:
            variant.uc_value = int(value)
        elif type == proto.eCHAR:
            variant.c_value = int(value)
        elif type == proto.eBOOL:
            variant.b_value = bool(value)
        elif type == proto.eSTRING:
            variant.str_value = str(value)
        return variant


PROXY_MIN_COMPAT_VERSION = 4
PROXY_CONNECT_TIMEOUT_SECONDS = 10


class ServiceTransport:
    """Virtual transport that tunnels through ServiceMessage on a primary connection."""

    def __init__(self, primary_connection, service_id, instance_id):
        self._primary = primary_connection
        self._service_id = service_id
        self._instance_id = instance_id
        self._is_connected = False
        self._is_closed = False
        self._pending_sends = []
        self._connect_timer = None
        self.on_message = None
        self.on_open = None
        self.on_close = None
        self.on_error = None
        self.url = 'service://' + str(service_id) + ':' + str(instance_id)

    def send(self, data_bytes):
        if self._is_closed:
            return
        if self._is_connected:
            self._primary.send_service_message(
                self._service_id, self._instance_id,
                proto.ServiceMessage.eData, data_bytes)
        else:
            self._pending_sends.append(data_bytes)

    def close(self):
        if self._is_closed:
            return
        self._cancel_connect_timer()
        self._is_closed = True
        self._is_connected = False
        self._primary.send_service_message(
            self._service_id, self._instance_id,
            proto.ServiceMessage.eDisconnect)

    def connect(self):
        self._connect_timer = threading.Timer(PROXY_CONNECT_TIMEOUT_SECONDS, self._handle_connect_timeout)
        self._connect_timer.daemon = True
        self._connect_timer.start()
        self._primary.send_service_message(
            self._service_id, self._instance_id,
            proto.ServiceMessage.eConnect)

    def run_forever(self, **kwargs):
        pass  # Service transports don't have their own event loop

    def on_service_message(self, service_msg):
        if service_msg.kind == proto.ServiceMessage.eConnected:
            self._cancel_connect_timer()
            self._is_connected = True
            for pending in self._pending_sends:
                self._primary.send_service_message(
                    self._service_id, self._instance_id,
                    proto.ServiceMessage.eData, pending)
            self._pending_sends = []
            if self.on_open:
                self.on_open(self)
        elif service_msg.kind == proto.ServiceMessage.eData:
            if self.on_message:
                self.on_message(self, service_msg.payload)
        elif service_msg.kind == proto.ServiceMessage.eDisconnect:
            self._cancel_connect_timer()
            self._is_connected = False
            self._is_closed = True
            self._remove_from_primary()
            if self.on_close:
                self.on_close(self)
        elif service_msg.kind == proto.ServiceMessage.eError:
            self._cancel_connect_timer()
            self._is_connected = False
            self._is_closed = True
            self._remove_from_primary()
            if self.on_error:
                self.on_error(self, 'Service error')
            if self.on_close:
                self.on_close(self)

    def _cancel_connect_timer(self):
        if self._connect_timer is not None:
            self._connect_timer.cancel()
            self._connect_timer = None

    def _handle_connect_timeout(self):
        if self._is_connected or self._is_closed:
            return
        self._is_closed = True
        self._remove_from_primary()
        if self.on_error:
            self.on_error(self, 'Proxy handshake timeout')
        if self.on_close:
            self.on_close(self)

    def _remove_from_primary(self):
        instance_key = str(self._service_id) + ':' + str(self._instance_id)
        self._primary._service_instances.pop(instance_key, None)


class Connection:
    def __init__(self, host, port, auto_reconnect, notification_listener=NotificationListener(),
                 encryption_parameters=dict()):
        self._host = host
        self._port = port
        self._system_name = ''
        self._application_name = ''
        self._cdp_version = ''
        self._system_use_notification = None
        self._compat_version = 0
        self._node_tree = NodeTree(self)
        self._structure_requests = Requests()
        self._time_request = Promise()
        self._time_diff = 0 #seconds
        self._last_time_diff_update = 0
        self._is_connected = False
        self._auto_reconnect = auto_reconnect
        self._notification_listener = notification_listener
        self._encryption_parameters = encryption_parameters
        self._challenge = ''
        self._credentials = dict()
        if 'use_encryption' in self._encryption_parameters and self._encryption_parameters['use_encryption']:
            protocol = 'wss://'
        else:
            protocol = 'ws://'
        self._ws = self._connect(protocol + host + ":" + str(port))
        self._re_auth_request = None
        self._available_services = {}
        self._service_instances = {}
        self._instance_counters = {}
        self._sibling_connections = {}
        self._sibling_subscriptions = []
        self._announced_siblings = set()
        self._ever_seen_siblings = set()
        self._system_node_id = None
        self._closing = False

    def _init_as_sibling(self, transport, primary_connection, addr, port):
        self._host = addr
        self._port = port
        self._system_name = ''
        self._application_name = ''
        self._cdp_version = ''
        self._system_use_notification = None
        self._compat_version = 0
        self._node_tree = NodeTree(self)
        self._structure_requests = Requests()
        self._time_request = Promise()
        self._time_diff = primary_connection._time_diff
        self._last_time_diff_update = primary_connection._last_time_diff_update
        self._is_connected = False
        self._auto_reconnect = False
        self._notification_listener = primary_connection._notification_listener
        self._encryption_parameters = {}
        self._challenge = ''
        self._credentials = primary_connection._credentials
        self._re_auth_request = None
        self._available_services = {}
        self._service_instances = {}
        self._instance_counters = {}
        self._sibling_connections = {}
        self._sibling_subscriptions = []
        self._announced_siblings = set()
        self._ever_seen_siblings = set()
        self._system_node_id = None
        self._primary_connection = primary_connection
        self._ws = transport
        transport.on_message = self._handle_hello_message
        transport.on_error = self._on_error
        transport.on_close = self._on_close
        transport.on_open = self._on_open

    def _rebind_transport(self, transport):
        self._ws = transport
        self._is_connected = False
        self._challenge = ''
        self._time_request = Promise()
        transport.on_message = self._handle_hello_message
        transport.on_error = self._on_error
        transport.on_close = self._on_close
        transport.on_open = self._on_open

    def _is_sibling(self):
        return hasattr(self, '_primary_connection') and self._primary_connection is not None

    def node_tree(self):
        return self._node_tree

    def send_structure_request(self, node_id, node_path):
        p = Promise()
        self._structure_requests.add(node_path, p)
        if self._is_connected:
            self._update_time_difference()
            self._compose_and_send_structure_request(node_id)
        return p

    def send_value_request(self, node_id, fs, sample_rate):
        self._update_time_difference()
        self._compose_and_send_value_request(node_id, fs, sample_rate)

    def send_value_unrequest(self, node_id):
        self._update_time_difference()
        self._compose_and_send_value_request(node_id, 1, 0, True)

    def send_value(self, variant):
        self._update_time_difference()
        self._compose_and_send_value(variant)

    def send_event_request(self, node_id, starting_from=None):
        self._update_time_difference()
        self._compose_and_send_event_request(node_id, starting_from)

    def send_event_unrequest(self, node_id):
        self._update_time_difference()
        self._compose_and_send_event_request(node_id, None, True)

    def run_event_loop(self):
        self._ws.run_forever(sslopt=self._encryption_parameters)
        while self._auto_reconnect:
            sleep(1)
            self._ws = self._connect(self._ws.url)
            self._ws.run_forever(sslopt=self._encryption_parameters)

    def close(self):
        self._auto_reconnect = False
        self._closing = True
        self._destroy_proxy_state()
        self._cleanup_queued_requests(ConnectionError('Connection was closed'))
        self._ws.close()

    def server_time_difference(self):
        return self._time_diff

    def supports_proxy_protocol(self):
        return self._compat_version >= PROXY_MIN_COMPAT_VERSION

    def _connect(self, url):
        return websocket.WebSocketApp(url,
                                      on_message=self._handle_hello_message,
                                      on_error=self._on_error,
                                      on_close=self._on_close,
                                      on_open=self._on_open)

    def _on_error(self, ws, error):
        if not self._auto_reconnect:
            self._cleanup_queued_requests(ConnectionError(error))

    def _on_close(self, ws, close_status_code=None, close_msg=None):
        was_connected = self._is_connected
        self._is_connected = False
        if self._is_sibling():
            if was_connected:
                self._announce_sibling_disconnected()
        elif self._auto_reconnect:
            self._reset_proxy_transports()
        else:
            self._destroy_proxy_state()
        if not self._auto_reconnect:
            self._cleanup_queued_requests(ConnectionError("Connection was closed"))

    def _announce_sibling_disconnected(self):
        primary = self._primary_connection
        name = self._application_name
        if primary is None or not name:
            return
        if primary._closing:
            return
        if name not in primary._announced_siblings:
            return
        primary._announced_siblings.discard(name)
        primary._fire_sibling_event(name, SiblingEvent.DISCONNECTED)

    def _reset_proxy_transports(self):
        for transport in list(self._service_instances.values()):
            transport._cancel_connect_timer()
            transport._is_closed = True
            transport._is_connected = False
        self._service_instances.clear()
        self._instance_counters.clear()
        self._available_services.clear()
        for sibling in list(self._sibling_connections.values()):
            sibling._is_connected = False
            name = sibling._application_name
            if name and name in self._announced_siblings:
                self._announced_siblings.discard(name)
                self._fire_sibling_event(name, SiblingEvent.DISCONNECTED)
        self._node_tree._connecting_siblings.clear()

    def _destroy_proxy_state(self):
        for transport in list(self._service_instances.values()):
            transport._cancel_connect_timer()
            transport._is_closed = True
            transport._is_connected = False
            if transport.on_close:
                transport.on_close(transport)
        self._service_instances.clear()
        self._instance_counters.clear()
        self._available_services.clear()
        self._sibling_connections.clear()
        self._announced_siblings.clear()
        self._ever_seen_siblings.clear()
        self._node_tree._connecting_siblings.clear()
        self._node_tree._known_siblings.clear()

    def subscribe_to_sibling_changes(self, callback):
        if callback not in self._sibling_subscriptions:
            self._sibling_subscriptions.append(callback)

    def unsubscribe_from_sibling_changes(self, callback):
        if callback in self._sibling_subscriptions:
            self._sibling_subscriptions.remove(callback)

    def _fire_sibling_event(self, app_name, event):
        for callback in list(self._sibling_subscriptions):
            callback(app_name, event)

    def _on_open(self, ws):
        pass

    def _fetch_time_difference(self):
        def do_time_request():
            self._compose_and_send_time_request()
            return self._time_request

        def get_time_diff(time_samples):
            def get_best_sample():
                best_sample = None
                for sample in time_samples:
                    if best_sample is None or sample.ping < best_sample.ping:
                        best_sample = sample
                return best_sample
            return Promise(lambda resolve, reject: resolve(get_best_sample().diff))

        def calculate_time_diff(time_request_sent, response):
            time_response_received = time.time()
            client_time = time_response_received
            ping_time = time_response_received - time_request_sent
            server_time = response / nanoseconds_in_second + ping_time / 2.0
            time_diff = client_time - server_time  # time_diff in seconds
            Sample = namedtuple('Sample', 'ping, diff')
            return Promise(lambda resolve, reject: resolve(Sample(ping_time, time_diff)))

        def get_time_sample():
            time_request_sent = time.time()
            return do_time_request().then(lambda response: calculate_time_diff(time_request_sent, response))

        def get_time_samples():
            number_of_samples = 3
            time_samples = []
            promise = Promise()

            def get_more_samples_if_needed():
                def store_sample_and_get_more_if_needed(sample):
                    time_samples.append(sample)
                    return get_more_samples_if_needed()

                if len(time_samples) < number_of_samples:
                    return get_time_sample().then(store_sample_and_get_more_if_needed)
                else:
                    promise.do_resolve(time_samples)

            get_more_samples_if_needed()
            return promise

        return get_time_samples().then(get_time_diff)

    def _update_time_difference(self):
        maximum_time_diff_update_frequency = 10 #seconds

        def store_time_diff(time_diff):
            self._time_diff = time_diff
            self._last_time_diff_update = time.time()
            return Promise(lambda resolve, reject: resolve())

        if time.time() >= self._last_time_diff_update + maximum_time_diff_update_frequency:
            return self._fetch_time_difference().then(store_time_diff)
        else:
            return Promise(lambda resolve, reject: resolve())

    def _sync_time(self):
        self._is_connected = True
        self._ws.on_message = self._handle_container_message
        is_primary_reconnect = (self._node_tree._root_node is not None
                                and not self._is_sibling())
        if is_primary_reconnect:
            self._structure_requests.clear(ConnectionError('Reconnecting'))
            try:
                self._time_request.do_reject(ConnectionError('Reconnecting'))
            except Exception:
                pass
            self._time_request = Promise()
        self._update_time_difference().then(self._node_tree.update()).then(self._send_queued_requests())
        if self.supports_proxy_protocol() and not self._is_sibling():
            self._send_services_request()

    def _announce_sibling_connected(self):
        primary = self._primary_connection
        name = self._application_name
        if primary is None or not name:
            return
        if name in primary._announced_siblings:
            return
        primary._announced_siblings.add(name)
        if name in primary._ever_seen_siblings:
            primary._fire_sibling_event(name, SiblingEvent.RECONNECTED)
        else:
            primary._ever_seen_siblings.add(name)
            primary._fire_sibling_event(name, SiblingEvent.CONNECTED)

    def _send_services_request(self):
        data = proto.Container()
        data.message_type = proto.Container.eServicesRequest
        data.services_request.subscribe = True
        data.services_request.inactivity_resend_interval = 120
        self._ws.send(data.SerializeToString())

    def _handle_auth_response(self, ws=None, message=None):
        if message is None:
            message = ws
            ws = None
        data = proto.AuthResponse()
        data.ParseFromString(message)
        if data.result_code in (data.eGranted, data.eGrantedPasswordWillExpireSoon):
            self._sync_time()
        else:
            auth_request = AuthRequest(host=self._host, port=self._port, system_name=self._system_name,
                                       application_name=self._application_name, cdp_version=self._cdp_version,
                                       system_use_notification=self._system_use_notification,
                                       user_auth_result=UserAuthResult(code=data.result_code,
                                                                       text=data.result_text,
                                                                       additional_credentials=data.additional_challenge_response_required))
            auth_request.then(self._authenticate)
            self._notification_listener.credentials_requested(auth_request)

    def _authenticate(self, credentials):
        self._ws.on_message = self._handle_auth_response
        self._credentials = credentials
        self._compose_and_send_auth_request()

    def _re_authenticate(self, credentials):
        self._credentials = credentials
        self._compose_and_send_re_auth_request()

    def _handle_hello_message(self, ws=None, message=None):
        if message is None:
            message = ws
            ws = None
        if self._parse_hello_message(message):
            request = AuthRequest(host=self._host, port=self._port, system_name=self._system_name,
                                  application_name=self._application_name, cdp_version=self._cdp_version,
                                  system_use_notification=self._system_use_notification)
            request.then(self._handle_application_acceptance)
            self._notification_listener.application_acceptance_requested(request)
        else:
            self._cleanup_queued_requests(CommunicationError('Protocol mismatch'))

    def _handle_application_acceptance(self, message):
        if self._challenge:
            if self._is_sibling() and self._credentials:
                self._authenticate(self._credentials)
            else:
                request = AuthRequest(host=self._host, port=self._port, system_name=self._system_name,
                                      application_name=self._application_name, cdp_version=self._cdp_version,
                                      system_use_notification=self._system_use_notification,
                                      user_auth_result=UserAuthResult(code=AuthResultCode.CREDENTIALS_REQUIRED,
                                                                      text='Credentials required'))
                request.then(self._authenticate)
                self._notification_listener.credentials_requested(request)
        else:
            self._sync_time()

    def _handle_re_auth_request(self, message):
        if not self._re_auth_request:
            self._re_auth_request = AuthRequest(host=self._host, port=self._port, system_name=self._system_name,
                                                application_name=self._application_name, cdp_version=self._cdp_version,
                                                user_auth_result=UserAuthResult(code=AuthResultCode.REAUTHENTICATION_REQUIRED,
                                                                                text=message))
            self._re_auth_request.then(self._re_authenticate)
            self._notification_listener.credentials_requested(self._re_auth_request)

    def _handle_container_message(self, ws=None, message=None):
        if message is None:
            message = ws
            ws = None
        data = proto.Container()
        data.ParseFromString(message)
        if data.message_type == proto.Container.eStructureResponse:
            self._parse_structure_response(data.structure_response)
        elif data.message_type == proto.Container.eGetterResponse:
            self._parse_getter_response(data.getter_response)
        elif data.message_type == proto.Container.eStructureChangeResponse:
            self._parse_structure_change_response(data.structure_change_response)
        elif data.message_type == proto.Container.eCurrentTimeResponse:
            self._parse_current_time_response(data.current_time_response)
        elif data.message_type == proto.Container.eReauthResponse:
            self._parse_re_auth_response(data.re_auth_response)
        elif data.message_type == proto.Container.eEventResponse:
            self._parse_event_response(data.event_response)
        elif data.message_type == proto.Container.eRemoteError:
            self._parse_error_response(data.error)
        elif data.message_type == proto.Container.eServicesNotification:
            self._parse_services_notification(data.services_notification)
        elif data.message_type == proto.Container.eServiceMessage:
            for msg in data.service_message:
                self._route_service_message(msg)
        else:
            logging.info('Unsupported message type received')

    def _parse_getter_response(self, response):
        for variant in response:
            node = self._node_tree.find_by_id(variant.node_id)
            node._update_value(variant)

    def _parse_structure_change_response(self, response):
        needs_system_refetch = False
        for node_id in response:
            if (self._system_node_id is not None
                    and node_id == self._system_node_id
                    and not self._is_sibling()):
                needs_system_refetch = True
                continue
            node = self._node_tree.find_by_id(node_id)
            if node is not None:
                node._update()
        if needs_system_refetch:
            self._refetch_system_structure()

    def _refetch_system_structure(self):
        self._node_tree._fetch_system().then(self._node_tree._get_root_node)

    def _parse_current_time_response(self, response):
        self._time_request.do_resolve(response)

    def _parse_event_response(self, response):
        for event_info in response:
            for node_id in event_info.node_id:
                node = self._node_tree.find_by_id(node_id)
                if node is not None:
                    node._update_event(event_info)

    def _parse_re_auth_response(self, response):
        if response.result_code not in (response.eGranted, response.eGrantedPasswordWillExpireSoon):
            self._re_auth_request = AuthRequest(host=self._host, port=self._port, system_name=self._system_name,
                                                application_name=self._application_name, cdp_version=self._cdp_version,
                                                user_auth_result=UserAuthResult(code=response.result_code,
                                                                                text=response.result_text,
                                                                                additional_credentials=response.additional_challenge_response_required))
            self._re_auth_request.then(self._re_authenticate)
            self._notification_listener.credentials_requested(self._re_auth_request)
        else:
            self._re_auth_request = None

    def _parse_error_response(self, error):
        if error.code == proto.eAUTH_RESPONSE_EXPIRED:
            self._challenge = error.challenge
            self._handle_re_auth_request(error.text)
        elif error.code == proto.eINVALID_REQUEST:
            self._cleanup_queued_requests(InvalidRequestError(error.text))
        elif error.code == proto.eUNSUPPORTED_CONTAINER_TYPE:
            self._cleanup_queued_requests(CommunicationError(error.text))
        elif error.code == proto.eNODE_NOT_FOUND:
            # Do NOT clear the entire queue on NODE_NOT_FOUND. This error
            # typically means a stale node_id was sent (e.g. after a sibling
            # restart where the new server assigned different ids). The
            # recovering _update_recursively chain will re-send the same
            # node_path with a fresh id and its response will resolve any
            # pending queue entry for that path. Clearing the queue here
            # would reject the test's still-valid find_node promise.
            pass

    def _parse_services_notification(self, notification):
        self._available_services.clear()
        for service in notification.services:
            self._available_services[service.service_id] = service
        self._node_tree.try_connect_pending_siblings()

    def _route_service_message(self, service_msg):
        instance_key = str(service_msg.service_id) + ':' + str(service_msg.instance_id)
        transport = self._service_instances.get(instance_key)
        if transport is not None:
            transport.on_service_message(service_msg)

    def _allocate_instance_id(self, service_id):
        next_id = self._instance_counters.get(service_id, 0)
        self._instance_counters[service_id] = next_id + 1
        return next_id

    def send_service_message(self, service_id, instance_id, kind, payload=None):
        if not self._is_connected:
            return
        data = proto.Container()
        data.message_type = proto.Container.eServiceMessage
        msg = data.service_message.add()
        msg.service_id = service_id
        msg.instance_id = instance_id
        msg.kind = kind
        if payload is not None:
            msg.payload = payload
        self._ws.send(data.SerializeToString())

    def find_proxy_service(self, addr, port):
        port_str = str(port)
        for service in self._available_services.values():
            if (service.type == 'websocketproxy' and
                service.metadata.get('proxy_type') == 'studioapi' and
                service.metadata.get('ip_address') == addr and
                service.metadata.get('port') == port_str):
                return service
        return None

    def connect_via_proxy(self, addr, port):
        transport = self._create_service_transport(addr, port)
        if transport is None:
            return Promise(lambda resolve, reject: reject(
                NotFoundError("No proxy service for " + addr + ":" + str(port))))

        sibling = Connection.__new__(Connection)
        sibling._init_as_sibling(transport, self, addr, port)

        sibling_key = addr + ':' + str(port)
        self._sibling_connections[sibling_key] = sibling

        transport.connect()
        return Promise(lambda resolve, reject: resolve(sibling))

    def rebind_sibling_via_proxy(self, sibling, addr, port):
        transport = self._create_service_transport(addr, port)
        if transport is None:
            return Promise(lambda resolve, reject: reject(
                NotFoundError("No proxy service for " + addr + ":" + str(port))))

        sibling._rebind_transport(transport)
        transport.connect()
        return Promise(lambda resolve, reject: resolve(sibling))

    def _create_service_transport(self, addr, port):
        service = self.find_proxy_service(addr, port)
        if service is None:
            return None
        service_id = service.service_id
        instance_id = self._allocate_instance_id(service_id)
        instance_key = str(service_id) + ':' + str(instance_id)
        transport = ServiceTransport(self, service_id, instance_id)
        self._service_instances[instance_key] = transport
        return transport

    def _parse_hello_message(self, message):
        data = proto.Hello()
        data.ParseFromString(message)
        if data.compat_version < 1:
            logging.info('Unsupported protocol version ' + str(data.compat_version) + '.' + str(data.incremental_version))
            return False
        self._compat_version = data.compat_version
        self._system_name = data.system_name
        self._application_name = data.application_name
        self._cdp_version = str(data.cdp_version_major) + '.' + \
                            str(data.cdp_version_minor) + '.' + \
                            str(data.cdp_version_patch)
        self._challenge = data.challenge
        self._system_use_notification = data.system_use_notification
        return True

    def _parse_structure_response(self, response):
        for structure in response:
            node = self._node_tree.find_by_id(structure.info.node_id)
            node_path = node.path() if node is not None else None
            request = self._structure_requests.find(node_path)  # requests are stored with node path because node id can change between application reconnect
            if request is not None:
                self._structure_requests.remove(node_path)
                for p in request.promises:
                    p.do_resolve(structure)

    def _send_queued_requests(self):
        for request in list(self._structure_requests.get()):
            node_path = request.node_path
            if node_path is None:
                self._compose_and_send_structure_request(None)
                continue
            node = self._node_tree.find_by_path(node_path)
            if node is None:
                self._structure_requests.remove(node_path)
                for p in request.promises:
                    p.do_reject(NotFoundError("Node '" + node_path + "' no longer exists"))
                continue
            self._compose_and_send_structure_request(node._id())

    def _cleanup_queued_requests(self, error):
        self._time_request.reject(error)
        self._structure_requests.clear(error)

    def _compose_and_send_structure_request(self, node_id):
        data = proto.Container()
        data.message_type = proto.Container.eStructureRequest
        if node_id is not None:
            data.structure_request.append(node_id)
        self._ws.send(data.SerializeToString())

    def _compose_and_send_value_request(self, node_id, fs, sample_rate, stop=False):
        data = proto.Container()
        data.message_type = proto.Container.eGetterRequest
        value = proto.ValueRequest()
        value.node_id = node_id
        value.fs = fs
        if sample_rate != 0:
            value.sample_rate = sample_rate
        if stop:
            value.stop = stop
        data.getter_request.extend([value])
        self._ws.send(data.SerializeToString())

    def _compose_and_send_value(self, variant):
        data = proto.Container()
        data.message_type = proto.Container.eSetterRequest
        data.setter_request.extend([variant])
        self._ws.send(data.SerializeToString())

    def _compose_and_send_time_request(self):
        data = proto.Container()
        data.message_type = proto.Container.eCurrentTimeRequest
        self._ws.send(data.SerializeToString())

    def _compose_and_send_event_request(self, node_id, starting_from=None, stop=False):
        data = proto.Container()
        data.message_type = proto.Container.eEventRequest
        event_request = proto.EventRequest()
        event_request.node_id = node_id
        if starting_from is not None:
            event_request.starting_from = starting_from
        if stop:
            event_request.stop = stop
        data.event_request.extend([event_request])
        self._ws.send(data.SerializeToString())

    def _compose_auth_request(self, request):
        if not 'Username' in self._credentials:
            UnknownError("NotificationListener.credentials_requested() didn't return 'Username' entry")
        request.user_id = self._credentials['Username']
        if 'Password' in self._credentials:
            response = request.challenge_response.add()
            response.type = "PasswordHash"
            user_pass_hash = sha256(request.user_id.lower().encode() + b':' + self._credentials['Password'].encode()).digest()
            response.response = sha256(self._challenge + b':' + user_pass_hash).digest()
        return request

    def _compose_and_send_auth_request(self):
        request = proto.AuthRequest()
        self._compose_auth_request(request)
        self._ws.send(request.SerializeToString())

    def _compose_and_send_re_auth_request(self):
        container = proto.Container()
        container.message_type = proto.Container.eReauthRequest
        request = proto.AuthRequest()
        self._compose_auth_request(request)
        container.re_auth_request.CopyFrom(request)
        self._ws.send(container.SerializeToString())

class NodeTree:
    def __init__(self, connection):
        self._connection = connection
        self._root_node = None  # starts with application node as node tree is created for each application connection
        self._known_siblings = set()
        self._connecting_siblings = set()

    def root_node(self):
        if self._root_node is None:
            return self._fetch_system() \
                .then(self._set_root_node) \
                .then(self._update_node) \
                .then(self._announce_sibling_after_load) \
                .catch(self._reset_root_on_failure)
        return Promise(lambda resolve, reject: resolve(self._root_node))

    def _announce_sibling_after_load(self, node):
        if self._connection._is_sibling():
            self._connection._announce_sibling_connected()
        return Promise(lambda resolve, reject: resolve(node))

    def _reset_root_on_failure(self, error):
        self._root_node = None
        if self._connection._is_sibling():
            self._connection._is_connected = False
        return Promise(lambda resolve, reject: reject(error))

    def find_by_id(self, node_id):
        def find_node(node):
            if node._id() == node_id:
                return node
            for child in node._children:
                node = find_node(child)
                if node is not None:
                    return node
            return None

        if self._root_node is None:
            return None
        return find_node(self._root_node)

    def find_by_path(self, path):
        def find_node(node):
            tokens.pop(0)
            if not tokens:
                return node
            for child in node._children:
                if child.name() == tokens[0]:
                    return find_node(child)
            return None

        if self._root_node is None:
            return None
        tokens = path.split('.')
        return find_node(self._root_node)

    def update(self):
        if self._root_node is not None:
            return self._fetch_system() \
                .then(self._get_root_node) \
                .then(self._update_recursively)
        return Promise(lambda resolve, reject: resolve())

    def _update_recursively(self, node):
        def update_children(node):
            promises = []
            for child in node._children:
                if child._children or child.is_leaf():  # do not fetch more than needed
                    promises.append(self._update_recursively(child))
            return Promise.all(promises)

        return node._update().done(update_children)

    def _update_node(self, node):
        return node._update()

    def _set_root_node(self, system_structure):
        self._connection._system_node_id = system_structure.info.node_id
        if not self._root_node:
            local_app = self._find_local_app(system_structure.node)
            if local_app:
                self._root_node = Node(None, self._connection, local_app)
        if self._connection.supports_proxy_protocol() and not self._connection._is_sibling():
            self._discover_siblings(system_structure)
            self.try_connect_pending_siblings()
        return Promise(lambda resolve, reject: resolve(self._root_node))

    def _find_local_app(self, apps):
        for app in apps:
            if app.info.is_local:
                return app
        return None

    def _discover_siblings(self, system_structure):
        self._known_siblings = set()
        for app in system_structure.node:
            if not app.info.is_local and app.info.server_addr and app.info.server_port:
                key = app.info.server_addr + ':' + str(app.info.server_port)
                self._known_siblings.add(key)

    def try_connect_pending_siblings(self):
        if not self._known_siblings:
            return
        for key in list(self._known_siblings):
            if key in self._connecting_siblings:
                continue
            existing = self._connection._sibling_connections.get(key)
            if existing is not None and existing._is_connected:
                continue
            addr, port = self._split_sibling_key(key)
            service = self._connection.find_proxy_service(addr, port)
            if service is None:
                continue
            self._connecting_siblings.add(key)
            if existing is not None:
                promise = self._connection.rebind_sibling_via_proxy(existing, addr, port)
            else:
                promise = self._connection.connect_via_proxy(addr, port)
            promise.then(
                lambda sibling, k=key: self._on_sibling_connected(sibling, k)
            ).catch(
                lambda err, k=key: self._on_sibling_connect_failed(err, k)
            )

    def _split_sibling_key(self, key):
        addr, _, port = key.rpartition(':')
        return addr, int(port)

    def _on_sibling_connected(self, sibling_connection, key):
        logging.info('Sibling connected: ' + key)
        self._connecting_siblings.discard(key)
        sibling_connection.node_tree().root_node()

    def _on_sibling_connect_failed(self, err, key):
        logging.error('Sibling connection failed for ' + key + ': ' + str(err))
        self._connecting_siblings.discard(key)

    def _get_root_node(self, system_structure):
        self._connection._system_node_id = system_structure.info.node_id
        # On reconnect (primary auto-reconnect or sibling rebind) the new
        # server may have assigned a different node_id to the root app. Refresh
        # the cached root's id from the fresh system structure (matched by
        # name) so the subsequent _update_recursively can fetch with valid ids.
        # Children's ids are refreshed inside Node._update_structure via
        # name-based matching.
        if self._root_node is not None:
            local_app = self._find_local_app(system_structure.node)
            if local_app is not None and local_app.info.name == self._root_node.name():
                self._root_node._structure.info.node_id = local_app.info.node_id
        if self._connection.supports_proxy_protocol() and not self._connection._is_sibling():
            self._discover_siblings(system_structure)
            self.try_connect_pending_siblings()
        if self._connection._is_sibling():
            self._connection._announce_sibling_connected()
        return Promise(lambda resolve, reject: resolve(self._root_node))

    def _fetch_system(self):
        return self._connection.send_structure_request(None, None)


class Requests:
    def __init__(self):
        self._requests = []

    def get(self):
        return self._requests

    def add(self, node_path, promise):  # use node_path instead of node_id as this doesn't change after reconnect
        request = self.find(node_path)
        if request is None:
            Request = namedtuple('Request', 'node_path, promises')
            self._requests.append(Request(node_path, [promise]))
        else:
            if promise not in request.promises:
                request.promises.append(promise)

    def find(self, node_path):
        for r in self._requests:
            if r.node_path == node_path:
                return r
        return None

    def remove(self, node_path):
        request = self.find(node_path)
        self._requests.remove(request)

    def clear(self, error=UnknownError('Something has went wrong')):
        for request in self._requests:
            for p in request.promises:
                p.do_reject(error)
        del self._requests[:]
