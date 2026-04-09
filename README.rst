CDP-Client
==========

A simple python interface for the CDP Studio development platform that allows Python scripts to interact with CDP Applications - retrieve CDP Application structures and read-write object values. For more information about CDP Studio see https://cdpstudio.com/

The API makes heavy use of promise library for asynchronous operations. For more information see https://pypi.org/project/promise/

Installation
------------

::

    $ pip install cdp-client

Usage
-----

The example below shows how you subscribe to CDP signal value changes.

.. code:: python

    from cdp_client import cdp

    def on_value_changed(value, timestamp):
        print(value)
	
    def subscribe_to_value_changes(node):
        node.subscribe_to_value_changes(on_value_changed)
	
    client = cdp.Client(host='127.0.0.1')
    client.find_node('AppName.ComponentName.SignalName').then(subscribe_to_value_changes)
    client.run_event_loop()

The example below shows how you subscribe to CDP events.

.. code:: python

    from cdp_client import cdp

    def on_event_received(event_info):
        print(f"Event {event_info.id} from {event_info.sender}")
        print(f"Code: {event_info.code}, Timestamp: {event_info.timestamp}")
        if event_info.data:
            for data_item in event_info.data:
                print(f"  {data_item.name}: {data_item.value}")

    def subscribe_to_events(node):
        node.subscribe_to_events(on_event_received)

    client = cdp.Client(host='127.0.0.1')
    client.root_node().then(subscribe_to_events)
    client.run_event_loop()

Multi-Application Support
~~~~~~~~~~~~~~~~~~~~~~~~~

When connected to CDP 5.1 or later, the client can access all applications in a CDP system through a single connection. The client connects to one application and reaches the others through the server's proxy protocol — no additional ports or connections needed.

Subscribe to ``sibling_changes`` to react when sibling applications appear, disappear or come back. ``find_node()`` can then address nodes in any application that is currently reachable:

.. code:: python

    import threading
    from cdp_client import cdp

    def on_value_changed(value, timestamp):
        print(value)

    def subscribe(node):
        node.subscribe_to_value_changes(on_value_changed)

    def on_sibling_change(app_name, event):
        if event == cdp.SiblingEvent.CONNECTED:
            print('Sibling connected:', app_name)
            client.find_node(app_name + '.ComponentName.SignalName').then(subscribe)
        elif event == cdp.SiblingEvent.DISCONNECTED:
            print('Sibling disconnected:', app_name)
        elif event == cdp.SiblingEvent.RECONNECTED:
            print('Sibling reconnected:', app_name)
            client.find_node(app_name + '.ComponentName.SignalName').then(subscribe)

    client = cdp.Client(host='127.0.0.1')
    client.subscribe_to_sibling_changes(on_sibling_change)
    threading.Thread(target=client.run_event_loop, daemon=True).start()
    client.root_node()  # Triggers connection and sibling discovery

After a primary connection drop, ``DISCONNECTED`` is delivered for every previously reachable sibling and ``RECONNECTED`` is delivered as each sibling becomes reachable again. Previously returned ``Node`` objects from sibling applications stay valid across the drop and their value subscriptions are automatically re-issued to the server when the sibling reconnects.

When connected to CDP versions before 5.1, ``find_node()`` is limited to the connected application and ``sibling_changes`` events are never fired.

API
---

Before all examples, you need:

.. code:: python

    from cdp_client import cdp

Global API
~~~~~~~~~~

Client(host, port, auto_reconnect, notification_listener, encryption_parameters)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Arguments

    host - String for hosts ip address

    port - Optional port number to connect to. If not specified default port 7689 is used.

    auto_reconnect - Optional argument to enable/disable automatic reconnect when connection is lost. Defaults to True if not specified.

    notification_listener - NotificationListener object whose methods are called on different connection events (e.g. when server requires credentials)

    encryption_parameters - Optional argument to set encryption and its parameters, TLS certificates verification etc. Parameter is compatible with python websocket client 'sslopt' parameter. For more information see https://pypi.org/project/websocket_client

- Returns

    The connected client object.

- Usage example

    .. code:: python

        client = cdp.Client(host='127.0.0.1')

- Usage example with password authentication

    .. code:: python

        class MyListener(cdp.NotificationListener):
            def credentials_requested(self, request):
                if request.user_auth_result().code() == cdp.AuthResultCode.CREDENTIALS_REQUIRED:
                    # Do something to gather username and password variables (either sync or async way) and then call:
                    request.accept({'Username': 'test', 'Password': '12345678'});

        client = cdp.Client(host='127.0.0.1', notification_listener=MyListener())

- Usage example with password authentication and encryption in use, without server certificate verification

    .. code:: python

        import ssl

        class MyListener(cdp.NotificationListener):
            def credentials_requested(self, request):
                if request.user_auth_result().code() == cdp.AuthResultCode.CREDENTIALS_REQUIRED:
                    # Do something to gather username and password variables (either sync or async way) and then call:
                    request.accept({'Username': 'test', 'Password': '12345678'});

        client = cdp.Client(host='127.0.0.1', notification_listener=MyListener(),
                            encryption_parameters={'use_encryption': True, 'cert_reqs': ssl.CERT_NONE})


- Usage example with password authentication and encryption in use, with server certificate verification

    .. code:: python

        import ssl

        class MyListener(cdp.NotificationListener):
            def credentials_requested(self, request):
                if request.user_auth_result().code() == cdp.AuthResultCode.CREDENTIALS_REQUIRED:
                    # Do something to gather username and password variables (either sync or async way) and then call:
                    request.accept({'Username': 'test', 'Password': '12345678'});

        client = cdp.Client(host='127.0.0.1', notification_listener=MyListener(),
                            encryption_parameters={'use_encryption': True,
                                                   'cert_reqs': ssl.CERT_REQUIRED,
                                                   'ca_certs': 'StudioAPI.crt',
                                                   'check_hostname': False})

Instance Methods / Client
~~~~~~~~~~~~~~~~~~~~~~~~~

client.root_node()
^^^^^^^^^^^^^^^^^^

Gets the application Node object of the connected application.

- Returns

    Promise containing root Node object when fulfilled.

- Usage

    .. code:: python

        client.root_node().then(on_success).catch(on_error)

client.find_node(path)
^^^^^^^^^^^^^^^^^^^^^^

Searches for the node specified by full dot separated path. When connected to CDP 5.1 or later with proxy connections established, the path can address nodes in any application in the system. Otherwise, the requested node must reside in the connected application. Root node is not considered part of the path.

- Arguments

    path - Dot separated string to target node (e.g. 'AppName.ComponentName.SignalName')

- Returns

    Promise containing requested Node object when fulfilled. Otherwise NotFoundError when rejected.

- Usage

    .. code:: python

        client.find_node('AppName.ComponentName.SignalName').then(on_success).catch(on_error)

client.run_event_loop()
^^^^^^^^^^^^^^^^^^^^^^^

Runs the event loop that serves network communication layer for incoming/outgoing data. **This is a blocking call that must be run for any communication to happen.** The method can be cancelled by calling disconnect.

client.subscribe_to_sibling_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starts listening to sibling application lifecycle events when connected to CDP 5.1 or later. The callback receives an application name and one of the ``cdp.SiblingEvent`` values.

- Arguments

    callback - Function(app_name, event) where event is ``cdp.SiblingEvent.CONNECTED``, ``cdp.SiblingEvent.DISCONNECTED`` or ``cdp.SiblingEvent.RECONNECTED``.

- Usage

    .. code:: python

        def on_sibling_change(app_name, event):
            if event == cdp.SiblingEvent.CONNECTED:
                print('Sibling connected:', app_name)
            elif event == cdp.SiblingEvent.DISCONNECTED:
                print('Sibling disconnected:', app_name)
            elif event == cdp.SiblingEvent.RECONNECTED:
                print('Sibling reconnected:', app_name)

        client.subscribe_to_sibling_changes(on_sibling_change)

client.unsubscribe_from_sibling_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Stops listening to sibling application lifecycle events.

- Arguments

    callback - Function(app_name, event) that was previously subscribed.

client.disconnect()
^^^^^^^^^^^^^^^^^^^

Stops the event loop and closes the connection to connected application. This method also releases the blocking run_event_loop call.

Instance Methods / Node
~~~~~~~~~~~~~~~~~~~~~~~

node.name()
^^^^^^^^^^^

- Returns

    The name of the Node object. Names in a parent node are all unique.

node.path()
^^^^^^^^^^^

- Returns

    A dot separated path of the Node object starting with application name.

node.parent()
^^^^^^^^^^^^^

- Returns

    The parent Node object.

node.type()
^^^^^^^^^^^

- Returns

    The type of the Node object returned as one of the cdp.NodeType values.

node.class_name()
^^^^^^^^^^^^^^^^^

- Returns

    CDP class name as a string.

node.last_value()
^^^^^^^^^^^^^^^^^

- Returns

    The last known value received by the Node object.

node.set_value(value, timestamp)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sets a new value for the Node object. Timestamp will be ignored in current implementation.

- Arguments

    value - New value

    timestamp - UTC time in nanoseconds since Epoch

node.is_read_only()
^^^^^^^^^^^^^^^^^^^

- Returns

    False if nodes value cannot be set, otherwise True.

node.is_leaf()
^^^^^^^^^^^^^^

- Returns

    True if node doesn't have any children, otherwise False.

node.child(name)
^^^^^^^^^^^^^^^^

- Arguments

    name - Child nodes name to search for

- Returns

    Promise containing requested Node object when fulfilled.

- Usage

    .. code:: python

        node.child('NodeName').then(on_success).catch(on_error)

node.children()
^^^^^^^^^^^^^^^

- Returns

    Promise containing all children of this Node object when fulfilled.

- Usage

    .. code:: python

        node.children().then(on_success).catch(on_error)

node.for_each_child(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Loops through all children and calls callback function for each of them

- Arguments

    callback - Function(node)

- Returns

    Promise containing all children of this Node object when fulfilled.

- Usage

    .. code:: python

        def on_callback(child):
            do something

        node.for_each_child(on_callback)

node.subscribe_to_structure_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starts listening structure changes and passes the changes to provided callback funtion

- Arguments

    callback - Function(added_nodes, removed_nodes) where added_nodes and removed_nodes is a list

- Usage

    .. code:: python

        def on_change(added_nodes, removed_nodes):
            do something

        node.subscribe_to_structure_changes(on_change)

node.subscribe_to_value_changes(callback, fs=5, sample_rate=0)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starts listening value changes and passes the changes to provided callback function

- Arguments

    callback - Function(value, timestamp)

    fs - Maximum frequency that value updates are expected (controls how many changes are sent in a single packet). Defaults to 5 hz.
    
    sample_rate - Maximum amount of value updates sent per second (controls the amount of data transferred). Zero means all samples must be provided. Defaults to 0.

- Usage

    .. code:: python

        def on_change(value, timestamp):
            do something

        node.subscribe_to_value_changes(on_change)


node.unsubscribe_from_structure_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Stops listening previously subscribed structure changes

- Arguments

    callback - Function(added_nodes, removed_nodes) where added_nodes and removed_nodes is a list

- Usage

    .. code:: python

        def on_change(added_nodes, removed_nodes):
            do something

        node.unsubscribe_from_structure_changes(on_change)

node.unsubscribe_from_value_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Stops listening previously subscribed value changes

- Arguments

    callback - Function(value, timestamp)

- Usage

    .. code:: python

        def on_change(value, timestamp):
            do something
	
        node.unsubscribe_from_value_changes(on_change)

node.subscribe_to_events(callback, starting_from=None)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starts listening to events from this node and its children, passing event information to the provided callback function

- Arguments

    callback - Function(event_info) where event_info contains id, sender, code, timestamp, and optional data fields

    starting_from - Optional timestamp to start receiving events from (in nanoseconds since Epoch). Defaults to None for current events.

- Usage

    .. code:: python

        def on_event(event_info):
            print(f"Event {event_info.id} from {event_info.sender}")
            print(f"Code: {event_info.code}, Timestamp: {event_info.timestamp}")
            if event_info.data:
                for data_item in event_info.data:
                    print(f"  {data_item.name}: {data_item.value}")

        node.subscribe_to_events(on_event)

node.unsubscribe_from_events(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Stops listening to previously subscribed events

- Arguments

    callback - Function(event_info) that was previously subscribed

- Usage

    .. code:: python

        def on_event(event_info):
            print(f"Event received: {event_info.id}")

        node.unsubscribe_from_events(on_event)

Notification Listener
~~~~~~~~~~~~~~~~~~~~~

To handle different connection events (like prompt user to accept a system use notification message or request user to enter credentials for authentication or idle lockout re-authentication) a notification_listener parameter must be provided to the Client.
The notification_listener parameter must be a object of type class cdp.NotificationListener.

class NotificationListener
^^^^^^^^^^^^^^^^^^^^^^^^^^

    .. code:: python

        class NotificationListener:
            def application_acceptance_requested(self, request=AuthRequest()):
                request.accept()

            def credentials_requested(self, request=AuthRequest()):
                raise NotImplementedError("NotificationListener credentials_requested() not implemented!")

NotificationListener.application_acceptance_requested(self, request=AuthRequest())
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Called by Client when new application TLS or plain TCP connection is established.
Can be used to prompt the user a System Use Notification (a message that can be configured in CDP Studio Security settings).

- Arguments

    request - a object that has method accept() that should be called to accept the connection and a reject() to reject the connection.

- Usage

    .. code:: python

        class MyListener(cdp.NotificationListener):
            def application_acceptance_requested(self, request):
                if request.system_use_notification():
                    # Pop up a System Use Notification message and ask for confirmation to continue,
                    # then based on the user answer call either request.accept() or request.reject()
                else:
                    request.accept()

        client = cdp.Client(host='127.0.0.1', port=7689, notification_listener=MyListener())

NotificationListener.credentials_requested(self, request=AuthRequest())
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Called by Client when server is requesting credentials (authentication or idle lockout re-authentication).

- Arguments

    request - a object that has method accept(data=dict()) that should be called (with credentials) for authentication try, and also a method reject() to reject the connection.

- Usage

    .. code:: python

        class MyListener(cdp.NotificationListener):
            def credentials_requested(self, request):
                if request.user_auth_result().code() == cdp.AuthResultCode.CREDENTIALS_REQUIRED:
                    # Do something to gather username and password variables (either sync or async way) and then call:
                    request.accept({'Username': 'test', 'Password': '12345678'});
                if request.user_auth_result().code() == cdp.AuthResultCode.REAUTHENTICATION_REQUIRED:
                    # Pop user a message that idle lockout was happened and server requires new authentication to continue:
                    request.accept({'Username': 'test', 'Password': '12345678'});

        client = cdp.Client(host='127.0.0.1', port=7689, notification_listener=MyListener())

Tests
-----

To run the test suite execute the following command in package root folder:

.. code:: sh

    $ python -m unittest discover cdp_client.tests -v

License
-------

`MIT
License <https://github.com/CDPTechnologies/PythonCDPClient/blob/master/LICENSE.txt>`__
