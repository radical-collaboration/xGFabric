#!/usr/bin/env python3

'''
This file implements a xGFabric HPC service endpoint.  The service can be
contacted via a REST API.

    register_client() -> str

        REST: GET /register_client
        returns: a unique ID to identify the client on further requests.

        Register client and return a unique client ID.  That ID is required for
        all further requests.

      - use cookie instead of client id
      - add authorization and authentication
'''


import fastapi

import sys
import uvicorn

from typing import List, Dict, Optional

import radical.utils as ru
import radical.pilot as rp


# ------------------------------------------------------------------------------
#
class _Client(object):

    # --------------------------------------------------------------------------
    #
    def __init__(self, log: ru.Logger) -> None:

        self._log   : ru.Logger = log
        self._uid   : str       = ru.generate_id('client')

        self._pilots: Dict[str, rp.Pilot] = dict()  # pilot_id -> pilot
        self._data  : Dict[str, str]      = dict()  # uuid     -> url


    # --------------------------------------------------------------------------
    #
    @property
    def uid(self) -> str:
        return self._uid


    # --------------------------------------------------------------------------
    #
    def _lookup(self, url: str) -> Optional[str]:

        try:
            return next(k for k, v in self._data.items() if v == url)

        except StopIteration:
            return None


    # --------------------------------------------------------------------------
    #
    def register_data(self, urls: List[str]) -> None:

        self._log.debug('%s: register %d urls', self._uid, len(urls))

        rep = list()
        for url in urls:

            key = self._lookup(url)

            if key:
                self._log.warn('%s: url is known  : %s - %s', self.uid, key, url)

            else:
                key = ru.generate_id('%s.url' % self._uid)
                self._log.info('%s: registered    : %s - %s', self.uid, key, url)

            rep.append(key)

        return rep


# ------------------------------------------------------------------------------
#
class Service(object):

    # --------------------------------------------------------------------------
    #
    def __init__(self) -> None:

        self._clients : Dict[str, _Client] = dict()
        self._log     : ru.Logger          = ru.Logger('xgfabric.hpc.service',
                                                       level='DEBUG', path='service.log')
        self._app     : fa.FastAPI         = fastapi.FastAPI()

        self._log.debug('test')


    # --------------------------------------------------------------------------
    #
    @property
    def app(self) -> fastapi.FastAPI:
        return self._app


    # --------------------------------------------------------------------------
    #
    def register_client(self) -> str:
        '''
        parameters:

        returns:
            str: unique ID identifying the registered client
        '''

        client = _Client(log=self._log)
        self._clients[client.uid] = client

        self._log.debug('register client: %s', client.uid)

        return client.uid


    # --------------------------------------------------------------------------
    #
    def register_data(self, cid: str, urls: List[str]) -> str:
        '''
        parameters:
           cid:str       : client ID
           urls:List[str]: urls to register

        returns:
           uids:str      : uids of the registered urls
        '''

        client = self._clients.get(cid)
        if not client:
            raise ValueError('unknown client cid %s' % cid)

        return client.register_data(urls)


# ------------------------------------------------------------------------------
#
if __name__ == '__main__':

    service = Service()


    @service.app.get("/register_client")
    def register_client() -> str:
        """
        Register a new client
        request: GET /register_client
        response: a new client ID (str)
        """

        uid = service.register_client()
        print('--- uid:', uid)
        return uid


    @service.app.put("/register_data/{cid}")
    def register_data(cid: str, urls: List[str]) -> List[str]:
        """
        register some data URLs
        request: PUT /{cid}/
            cid: client ID as obtained by `register`
            data: json serialized list of URLs to register
        response: list of UIDs for the registered URLs
        """
        return service.register_data(cid, urls)

    port = 5000
    sys.stdout.write('url: http://localhost:%d/\n' % port)
    sys.stdout.flush()
    uvicorn.run(service.app, port=port, access_log=False)


# ------------------------------------------------------------------------------

