#!/usr/bin/env python3

import sys

import radical.utils as ru


# ------------------------------------------------------------------------------
#
if __name__ == '__main__':

    addr  = sys.argv[1]
    fname = sys.argv[2]

    uid = None
    if len(sys.argv) > 3:
        uid = sys.argv[3]

    with open(fname) as fin:
        data = fin.read()

    c = ru.zmq.Client(url=addr)

    if not uid:
        uid = c.request('register')
        print('uid: %s' % uid)

    result = c.request('register_data', uid=uid, data=data)

    print(1, result)


# ------------------------------------------------------------------------------

