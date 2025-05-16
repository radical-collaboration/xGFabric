#!/usr/bin/env python3

import sys

import xgfabric.service as xs


'''
This file implements a xGFabric HPC service endpoint.  The service can be
contacted via a REST API.

    register() -> str

        REST: GET /register
        returns: a unique ID to identify the client on further requests.

        Register client and return a unique client ID.  That ID is required for
        all further requests.

      - use cookie instead of client id
      - add authorization and authentication
'''

# ------------------------------------------------------------------------------
#
if __name__ == '__main__':

    if len(sys.argv) < 2:
        raise ValueError('no config file specified')

    s = xs.ServiceEndpoint(cfg_file=sys.argv[1])
    addr = s.start()
    print('=== service endpoint: %s' % addr)
    s.wait()


# ------------------------------------------------------------------------------

