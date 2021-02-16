CDP-Client
==========

A simple python interface for the CDP Studio development platform that allows Python scripts to interact with CDP Applications - retrieve CDP Application structures and read-write object values. For more information about CDP Studio see https://cdpstudio.com/

The API makes heavy use of promise library for asynchronous operations. For more information see https://pypi.python.org/pypi/promise

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

API
---

Before all examples, you need:

.. code:: python

    from cdp_client import cdp

Global API
~~~~~~~~~~

Client(host, port, auto_reconnect, user_id, password, use_encryption, encryption_parameters)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Arguments

    host - String for hosts ip address

    port - Optional port number to connect to. If not specified default port 7689 is used.

    auto_reconnect - Optional argument to enable/disable automatic reconnect when connection is lost. Defaults to True if not specified.

    user_id - Optional argument to use when server requires authentication - user id (username)

    password  - Optional argument to use when server requires authentication - user password

    use_encryption - Optional boolean argument to set when server uses encryption. Defaults to False.

    encryption_parameters - Optional argument to set encryption parameters, like TLS certificates verification. Parameter is compatible with python websocket client 'sslopt' parameter. For more information see https://pypi.org/project/websocket_client

- Returns

    The connected client object.

- Usage example

    .. code:: python

        client = cdp.Client(host='127.0.0.1')

- Usage example with password authentication

    .. code:: python

        client = cdp.Client(host='127.0.0.1', user_id='test', password='12345678')

- Usage example with password authentication and encryption in use, without server certificate verification

    .. code:: python

        import ssl

        client = cdp.Client(host='127.0.0.1', user_id='test', password='12345678',
                            use_encryption=True,
                            encryption_parameters={'cert_reqs': ssl.CERT_NONE})


- Usage example with password authentication and encryption in use, with server certificate verification

    .. code:: python

        import ssl

        client = cdp.Client(host='127.0.0.1', user_id='test', password='12345678',
                            use_encryption=True,
                            encryption_parameters={'cert_reqs': ssl.CERT_REQUIRED,
                                                   'ca_certs': 'StudioAPI.crt',
                                                   'check_hostname': False},

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

Searches for the node specified by full dot separated path. **The requested node must reside in the application client was connected to. Root node is not considered part of the path.**

- Arguments

    path - Dot separated string to target node

- Returns

    Promise containing requested Node object when fulfilled. Otherwise NotFoundError when rejected.

- Usage

    .. code:: python

        client.find_node('AppName.ComponentName.SignalName').then(on_success).catch(on_error)

client.run_event_loop()
^^^^^^^^^^^^^^^^^^^^^^^

Runs the event loop that serves network communication layer for incoming/outgoing data. **This is a blocking call that must be run for any communication to happen.** The method can be cancelled by calling disconnect.

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

node.subscribe_to_value_changes(callback)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starts listening value changes and passes the changes to provided callback function

- Arguments

    callback - Function(value, timestamp)

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

Tests
-----

To run the test suite execute the following command in package root folder:

.. code:: sh

    $ python setup.py test

License
-------

`MIT
License <https://github.com/CDPTechnologies/PythonCDPClient/blob/master/LICENSE.txt>`__
