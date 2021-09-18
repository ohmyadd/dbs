import os
import codecs
import sys
import yaml
import netaddr
import itertools
from bs4 import BeautifulSoup
from pprint import pprint


def macgen():
    strbyte = ['%02x' % i for i in range(256)]
    for i in itertools.product(strbyte, repeat=5):
        yield "c0:" + ":".join(i)
    

src = sys.argv[1]
srcpath = os.path.join("../src", src)
srcname = src.split('.')[0]

appirpath = os.path.join("../ir/", srcname + '.app.yaml')
netirpath = os.path.join("../ir/", srcname + '.net.yaml')

macs = macgen()
macs.send(None)

with open(srcpath, 'rb') as txt:
    bp = BeautifulSoup(txt.read().replace(b'\xc2\xa0', b' '), 'xml')
    print(bp)


### app
apps = {}
for i in bp.select('mxCell[style*="shape=process"]'):
    try:
        # print(codecs.encode(i.attrs['value'].encode('utf-8'), 'hex'))
        v = yaml.full_load(i.attrs['value'])
    except:
        print(codecs.encode(i.attrs["value"].encode('utf-8'), 'hex'))
        raise(BaseException())
    v.setdefault('networks', {}) 
    v.setdefault('hostname', v['name']) 
    v.setdefault('domainname', 'test.net') 
    v.setdefault('dns_search', 'test.net') 
    v.setdefault('dns', '8.8.8.8') 
    apps[i.attrs['id']] = v


### all the network, rectangle + diamond->diamond
# rectangle
networks = {}
pools = {}
for i in bp.select('mxCell[style*="shape=rectangle"]'):
    v = yaml.full_load(i.attrs['value'])
    name = i.attrs['id']
    subnet = v.get('subnet')
    gateway = v.get('gateway', str(netaddr.IPAddress(netaddr.IPNetwork(subnet).first + 1)))
    fakegateway = str(netaddr.IPAddress(netaddr.IPNetwork(subnet).last - 1))
    networks[name] = {'driver': 'ovn', 'driver_opts': {'com.ohmyadd.network.ovn.gateway': gateway},
                      'ipam': {'config': [{'subnet': subnet, 'gateway': fakegateway,
                                           'aux_addresses': {}}]}}
    pools[name] = []
# diamond -> diamond
for i in bp.select('mxCell[style*="edgeStyle=orthogonalEdgeStyle"][style*="startArrow=diamond"][style*="endArrow=diamond"]'):
    arrowid = i.attrs['id']
    source = i.attrs['source']
    target = i.attrs['target']
    j = bp.select('mxCell[parent="%s"]' % arrowid)[0]
    v = yaml.full_load(j.attrs['value'])

    name = arrowid
    subnet = v.get('subnet')
    gateway = v.get('gateway', str(netaddr.IPAddress(netaddr.IPNetwork(subnet).last - 2)))
    fakegateway = str(netaddr.IPAddress(netaddr.IPNetwork(subnet).last - 1))
    networks[name] = {'driver': 'ovn','driver_opts': {'com.ohmyadd.network.ovn.gateway': gateway},
                      'ipam': {'config': [{'subnet': subnet, 'gateway': fakegateway,
                                           'aux_addresses': {}}]}}
    pools[name] = []
    # connect app to net
    apps[source]['networks'][name] = {}
    apps[target]['networks'][name] = {}


# connect app to net
for i in bp.select('mxCell[style*="edgeStyle=orthogonalEdgeStyle"][style*="startArrow=oval"][style*="endArrow=open"]'):
    arrowid = i.attrs['id']
    source = i.attrs['source']
    target = i.attrs['target']
    j = bp.select('mxCell[parent="%s"]' % arrowid)
    if j:
        v = yaml.full_load(j[0].attrs['value'])
    else:
        v = {}

    if 'ip' in v:
        # networks[target]['ipam']['config'][0]['aux_addresses'][apps[source]['name']] = v['ip']
        net = {'ipv4_address': v['ip']}
        pools[target].append(v['ip'])
    else:
        net = {'ipv4_address': ''}
    apps[source]['networks'][target] = net
for k, v in apps.items():
   for x, y in v['networks'].items():
        if y.get('ipv4_address', ''):
            continue
        network = netaddr.IPNetwork(networks[x]['ipam']['config'][0]['subnet'])
        for i in range(network.first + 1, network.last):
            ip = str(netaddr.IPAddress(i))
            if ip not in pools[x]:
                pools[x].append(ip)
                break
        else:
            raise(subnet + 'pool full')
        y['ipv4_address'] = ip

pprint(networks)
pprint(apps)

apps = {v['name']: v for k,v in apps.items()}
{v.pop('name') for k, v in apps.items()}
app_cfg = {"version": "2.4", "networks": networks, "services": apps}

with open(appirpath, 'w') as txt:
    yaml.dump(app_cfg, txt)
