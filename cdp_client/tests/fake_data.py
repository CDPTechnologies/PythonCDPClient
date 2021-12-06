from cdp_client import cdp_pb2 as proto
from copy import copy
from hashlib import sha256

value1 = proto.VariantValue()
value1.node_id = 5
value1.d_value = 55
value1.timestamp = 777

value2 = proto.VariantValue()
value2.node_id = 5
value2.d_value = 66
value2.timestamp = 888

value1_node = proto.Node()
value1_node.info.node_id = 5
value1_node.info.name = "Value1"
value1_node.info.node_type = proto.CDP_PROPERTY
value1_node.info.value_type = proto.eDOUBLE
value1_node.info.flags = proto.Info.eNodeIsLeaf

comp1_node = proto.Node()
comp1_node.info.node_id = 9
comp1_node.info.name = "Comp1"
comp1_node.info.node_type = proto.CDP_COMPONENT
comp1_node.info.value_type = proto.eUNDEFINED
comp1_node.info.flags = proto.Info.eValueIsReadOnly

app1_node = proto.Node()
app1_node.info.node_id = 1
app1_node.info.name = "App1"
app1_node.info.node_type = proto.CDP_APPLICATION
app1_node.info.value_type = proto.eUNDEFINED
app1_node.info.is_local = True
app1_node.info.flags = proto.Info.eValueIsReadOnly | proto.Info.eNodeIsLeaf

app2_node = proto.Node()
app2_node.info.node_id = 2
app2_node.info.name = "App2"
app2_node.info.node_type = proto.CDP_APPLICATION
app2_node.info.value_type = proto.eUNDEFINED
app2_node.info.flags = proto.Info.eValueIsReadOnly

app3_node = proto.Node()
app3_node.info.node_id = 3
app3_node.info.name = "App3"
app3_node.info.node_type = proto.CDP_APPLICATION
app3_node.info.value_type = proto.eUNDEFINED
app3_node.info.flags = proto.Info.eValueIsReadOnly

system_node = proto.Node()
system_node.info.node_id = 0
system_node.info.name = "System"
system_node.info.node_type = proto.CDP_SYSTEM
system_node.info.value_type = proto.eUNDEFINED
system_node.info.flags = proto.Info.eValueIsReadOnly

hello_response = proto.Hello()
hello_response.system_name = "foo"
hello_response.compat_version = 1
hello_response.incremental_version = 0


def create_system_structure_response():
    response = proto.Container()
    response.message_type = proto.Container.eStructureResponse
    system = copy(system_node)
    system.node.extend([copy(app1_node), copy(app2_node)])
    response.structure_response.extend([system])
    return response


def create_app_structure_response():
    response = proto.Container()
    response.message_type = proto.Container.eStructureResponse
    app = copy(app2_node)
    app.node.extend([copy(value1_node)])
    response.structure_response.extend([app])
    return response


def create_structure_change_response(node_id):
    response = proto.Container()
    response.message_type = proto.Container.eStructureChangeResponse
    response.structure_change_response.extend([node_id])
    return response


def create_value_response():
    response = proto.Container()
    response.message_type = proto.Container.eGetterResponse
    response.getter_response.extend([value1])
    return response


def create_error_response():
    response = proto.Container()
    response.message_type = proto.Container.eRemoteError
    response.error.code = proto.eINVALID_REQUEST
    response.error.text = "foo"
    return response


def create_value_request(node_id):
    request = proto.Container()
    request.message_type = proto.Container.eGetterRequest
    value = proto.ValueRequest()
    value.node_id = node_id
    value.fs = 5
    request.getter_request.extend([value])
    return request


def create_value_unrequest(node_id):
    request = proto.Container()
    request.message_type = proto.Container.eGetterRequest
    value = proto.ValueRequest()
    value.node_id = node_id
    value.fs = 5
    value.stop = True
    request.getter_request.extend([value])
    return request


def create_time_request():
    request = proto.Container()
    request.message_type = proto.Container.eCurrentTimeRequest
    return request


def create_time_response(time):
    response = proto.Container()
    response.message_type = proto.Container.eCurrentTimeResponse
    response.current_time_response = time
    return response


def create_valid_hello_response(system_use_notification=''):
    response = proto.Hello()
    response.system_name = "foo"
    response.compat_version = 1
    response.incremental_version = 0
    response.system_use_notification = system_use_notification
    return response


def create_valid_hello_response_with_auth_required(challenge):
    response = proto.Hello()
    response.system_name = "foo"
    response.compat_version = 1
    response.incremental_version = 0
    response.challenge = challenge
    return response


def create_invalid_hello_response():
    response = proto.Hello()
    response.system_name = "foo"
    response.compat_version = 2
    response.incremental_version = 0
    return response


def create_structure_request(node_id = None):
    request = proto.Container()
    request.message_type = proto.Container.eStructureRequest
    if node_id is not None:
        request.structure_request.append(node_id)
    return request


def create_setter_request(variant_value):
    request = proto.Container()
    request.message_type = proto.Container.eSetterRequest
    request.setter_request.extend([variant_value])
    return request


def create_structure_change_request(node_id):
    request = proto.Container()
    request.message_type = proto.Container.eStructureRequest
    request.structure_request.append(node_id)
    return request


def create_password_auth_request(challenge, user_id, password):
    request = proto.AuthRequest()
    request.user_id = user_id
    response = request.challenge_response.add()
    response.type = "PasswordHash"
    user_pass_hash = sha256(user_id.encode().lower() + b':' + password.encode()).digest()
    response.response = sha256(challenge + b':' + user_pass_hash).digest()
    return request


def create_container_with_password_auth_request(challenge, user_id, password):
    request = proto.AuthRequest()
    request.user_id = user_id
    response = request.challenge_response.add()
    response.type = "PasswordHash"
    user_pass_hash = sha256(user_id.encode().lower() + b':' + password.encode()).digest()
    response.response = sha256(challenge + b':' + user_pass_hash).digest()
    container = proto.Container()
    container.message_type = proto.Container.eReAuthRequest
    container.re_auth_request.CopyFrom(request)
    return container


def create_auth_response_granted():
    response = proto.AuthResponse()
    response.result_code = response.eGranted
    return response


def create_auth_response_denied():
    response = proto.AuthResponse()
    response.result_code = response.eInvalidChallengeResponse
    return response


def create_auth_response_expired_error(challenge):
    response = proto.Container()
    response.message_type = proto.Container.eRemoteError
    response.error.code = proto.eAUTH_RESPONSE_EXPIRED
    response.error.text = "Session expired"
    response.error.challenge = challenge
    return response
