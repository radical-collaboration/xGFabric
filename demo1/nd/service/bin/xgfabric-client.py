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

    c = ru.zmq.Client(url=addr)

    if not uid:
        uid = c.request('register_client')
        print('uid: %s' % uid)

    result = c.request('register_fname', uid=uid, fname=fname)

    print(1, result)


# ------------------------------------------------------------------------------

