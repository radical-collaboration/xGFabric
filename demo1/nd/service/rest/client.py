#!/usr/bin/env python3

import pprint

import requests
import messages

urls = ['http://example.com']
res  = requests.get('http://localhost:5000/register_client')

if not res.ok:
    raise RuntimeError("Error: %s" % res.reason)

cid = res.json()
print('--- cid:', cid)
res = requests.put('http://localhost:5000/register_data/%s' % cid, json=urls)

if not res.ok:
    raise RuntimeError("Error: %s" % res.reason)

pprint.pprint(res.json())


# ------------------------------------------------------------------------------

