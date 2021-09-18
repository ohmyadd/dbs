import os
import time
import sys
import logging

import netaddr
import pyroute2
from flask import Flask, jsonify, request

from ovsdbapp import constants
from ovsdbapp.backend.ovs_idl import connection
from ovsdbapp.schema.open_vswitch import impl_idl as ovs_impl
from ovsdbapp.schema.ovn_northbound import impl_idl as north_impl


#idl = connection.OvsdbIdl.from_server("unix:/var/run/openvswitch/db.sock", 'Open_vSwitch')
idl = connection.OvsdbIdl.from_server("tcp:172.19.0.1:6640", 'Open_vSwitch')
ovs_conn = connection.Connection(idl=idl, timeout=constants.DEFAULT_TIMEOUT)
ovs = ovs_impl.OvsdbIdl(ovs_conn)

north_socket = "tcp:172.19.0.2:6641"
idl = connection.OvsdbIdl.from_server(north_socket, 'OVN_Northbound')
north_conn = connection.Connection(idl=idl, timeout=constants.DEFAULT_TIMEOUT)
north = north_impl.OvnNbApiIdlImpl(north_conn)

iproute = pyroute2.IPRoute()


app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)
app.logger.info("Application started")


# The API calls below are documented at
# https://github.com/docker/libnetwork/blob/master/docs/remote.md

# <-- Plugin activation, we activate both libnetwork and ipam plugins -->

@app.route('/Plugin.Activate', methods=['POST'])
def activate():
    json_response = {"Implements": ["NetworkDriver"]}
    # app.logger.debug("Activate response JSON=%s", json_response)
    return jsonify(json_response)


# <-- libnetwork plugin API -->

@app.route('/NetworkDriver.GetCapabilities', methods=['POST'])
def get_capabilities():
    json_response = {"Scope": "local", "ConnectivityScope": "local"}
    # app.logger.debug("GetCapabilities response JSON=%s", json_response)
    return jsonify(json_response)


@app.route('/NetworkDriver.CreateNetwork', methods=['POST'])
def create_network():
    data = request.get_json(force=True)
    # app.logger.debug("CreateNetwork JSON=%s", data)

    v4 = data['IPv4Data'][0]
    pool = netaddr.IPNetwork(v4['Pool'])
    gw = str(netaddr.IPAddress(netaddr.IPNetwork(v4['Gateway']).value))
    if 'com.ohmyadd.network.ovn.gateway' in data['Options']['com.docker.network.generic']:
        gw = data['Options']['com.docker.network.generic']['com.ohmyadd.network.ovn.gateway']

    uuid = north.dhcp_options_add(v4['Pool']).execute().uuid
    north.dhcp_options_set_options(uuid, lease_time='3600', server_mac='c0:ff:ee:00:00:03',
                                   server_id='192.168.100.1', router=gw).execute()

    external = {'dhcp': str(uuid), 'subnet': v4['Pool'], 'gw': gw}
    north.ls_add(data["NetworkID"], external_ids=external).execute()

    return jsonify({})

@app.route('/NetworkDriver.DeleteNetwork', methods=['POST'])
def delete_network():
    data = request.get_json(force=True)
    # app.logger.debug("DeleteNetwork JSON=%s", data)
    network_id = data['NetworkID']

    dhcpuuid = north.ls_get(network_id).execute().external_ids['dhcp']
    north.dhcp_options_del(dhcpuuid).execute()

    north.ls_del(network_id).execute()
    return jsonify({})


@app.route('/NetworkDriver.CreateEndpoint', methods=['POST'])
def create_endpoint():

    data = request.get_json(force=True)
    # app.logger.debug("CreateEndpoint JSON=%s", data)
    endpoint_id = data["EndpointID"]
    network_id = data["NetworkID"]
    interface = data["Interface"]

    # Get the addresses to use from the request JSON.
    address_ip4 = interface.get("Address")
    address_ip6 = interface.get("AddressIPv6")
    mac = interface.get('MacAddress')
    if not mac:
        mac = ':'.join(['c0', endpoint_id[:2], endpoint_id[2:4], endpoint_id[4:6],
                        endpoint_id[6:8], endpoint_id[8:10]])
    assert address_ip4 or address_ip6, "No address assigned for endpoint"
  
    dhcpuuid = north.ls_get(network_id).execute().external_ids['dhcp']
    dhcp = north.dhcp_options_get(dhcpuuid).execute().uuid
    # lsp
    ip = str(netaddr.IPAddress(netaddr.IPNetwork(address_ip4).value))
    address = mac + ' ' + ip
    north.lsp_add(network_id, endpoint_id, addresses=[address],
                  dhcpv4_options=dhcp, external_ids={'mac': mac, 'ip': ip}).execute()
    return jsonify({"Interface": {'MacAddress': mac}})


@app.route('/NetworkDriver.DeleteEndpoint', methods=['POST'])
def delete_endpoint():
    data = request.get_json(force=True)
    # app.logger.debug("DeleteEndpoint JSON=%s", data)
    endpoint_id = data["EndpointID"]
    north.lsp_del(endpoint_id).execute()

    return jsonify({})

@app.route('/NetworkDriver.EndpointOperInfo', methods=['POST'])
def endpoint_oper_info():
    json_data = request.get_json(force=True)
    # app.logger.debug("EndpointOperInfo JSON=%s", json_data)
    endpoint_id = json_data["EndpointID"]
    return jsonify({'Value': {}})


@app.route('/NetworkDriver.Join', methods=['POST'])
def join():
    data = request.get_json(force=True)
    # app.logger.debug("Join JSON=%s", data)
    network_id = data["NetworkID"]
    endpoint_id = data["EndpointID"]
    sandbox_key = data["SandboxKey"]

    gw = north.ls_get(network_id).execute().external_ids['gw']
    ids = north.lsp_get(endpoint_id).execute().external_ids
    mac = ids['mac']
    ip = ids['ip']

    ifacename = endpoint_id[:14]
    iproute.link('add', ifname=ifacename+'l', kind='veth', peer={'ifname': ifacename+'r'})
    iproute.link('set', ifname=ifacename+'r', address=mac)
    iproute.link('set', ifname=ifacename+'l', state='up')
    ovs.add_port('br-int', ifacename+'l').execute()
    ovs.db_set('Interface', ifacename+'l', ('external_ids', {'iface-id': endpoint_id})).execute()

    if ip == gw:
        app.logger.debug(ip + '===' + gw)
        gw = ''
    json_response = {
        "InterfaceName": {
            "DstPrefix": 'eth',
            "SrcName": ifacename+'r'
        },
        "Gateway": gw,
        "GatewayIPv6": "",
        "StaticRoutes": []
        #"StaticRoutes": [{'Destination': '0.0.0.0/0',
        #                  'RouteType': 0,
        #                  'NextHop': gw}]
    }
    return jsonify(json_response)

@app.route('/NetworkDriver.Leave', methods=['POST'])
def leave():
    json_data = request.get_json(force=True)
    # app.logger.debug("Leave JSON=%s", json_data)
    endpoint_id = json_data["EndpointID"]

    ifacename = endpoint_id[:14]
    ovs.del_port(ifacename+'l').execute()
    iproute.link('del', ifname=ifacename+'l')
    return jsonify({})


@app.route('/NetworkDriver.DiscoverNew', methods=['POST'])
def discover_new():
    json_data = request.get_json(force=True)
    # app.logger.debug("DiscoverNew JSON=%s", json_data)
    return jsonify({})


@app.route('/NetworkDriver.DiscoverDelete', methods=['POST'])
def discover_delete():
    json_data = request.get_json(force=True)
    # app.logger.debug("DiscoverNew JSON=%s", json_data)
    return jsonify({})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8089)
