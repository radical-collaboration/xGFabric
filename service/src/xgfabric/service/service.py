
import time

import radical.utils as ru
import radical.pilot as rp

from .pilot_controller import PilotController


# ------------------------------------------------------------------------------
#
class _Client(ru.TypedDict):

    _schema = {
        'uid'    : str,              # client uid
        't_reg'  : float,            # registration time
        'fname'  : str,              # file name
        'data'   : str,              # fake input data
        'pid'    : str,              # pilot id
    }

    _defaults = {
        'uid'    : None,
        't_reg'  : None,
        'fname'  : None,
        'data'   : None,
        'pid'    : None,
    }


# ------------------------------------------------------------------------------
#
class ServiceEndpoint(ru.zmq.Server):

    #---------------------------------------------------------------------------
    #
    def __init__(self, url: str):

        super().__init__(url)

        self._clients = dict()
        self._session = None
        self._tmgr    = None
        self._pmgr    = None
        self._p_ctrl  = None

        self.register_request('register_client', self.register_client)
        self.register_request('register_fname',  self.register_fname)


    # --------------------------------------------------------------------------
    #
    def __del__(self):

        if self._session:
            self._session.close()


    # --------------------------------------------------------------------------
    #
    def start(self):

        self._session = rp.Session()
        self._tmgr    = rp.TaskManager(session=self._session)
        self._pmgr    = rp.PilotManager(session=self._session)

        self._p_ctrl  = PilotController(self._pmgr, self._tmgr,
                                        {'resource_type': 'local.localhost',
                                         'nodes'        : 8,
                                         'max_runtime'  : 600})
        self._p_ctrl.start_initial_pilot()

        super().start()
        return self.addr


    # --------------------------------------------------------------------------
    #
    def get_clients(self, uid:str) -> _Client:

        assert uid in self._clients, 'unknown client [%s]' % uid
        return self._clients[uid]


    # --------------------------------------------------------------------------
    #
    def register_client(self) -> str:

        client = _Client(uid=ru.generate_id('client'), t_reg=time.time())

        self._clients[client.uid] = client

        self._log.info('client %s registered', client.uid)

        return client.uid


    # --------------------------------------------------------------------------
    #
    def register_fname(self, uid:str, fname: str) -> str:

        client = self.get_clients(uid)

        with ru.ru_open(fname) as fin:
            data = fin.read()

        self._log.info('client %s registered %s', uid, len(data))

        client.fname = fname
        client.data  = data
        client.pid   = self._p_ctrl.start_pilot({'data': data})

        tds = list()
        td  = rp.TaskDescription()
        td.executable = '/bin/echo'
        td.arguments  = ['DATA:', data]
        tds.append(td)

        tasks = self._tmgr.submit_tasks(tds)
        self._tmgr.wait_tasks()

        res = list()
        for task in tasks:
            res.append(task.stdout)

        self._log.info('client %s result: %s', uid, res)

        return str(res)


# ------------------------------------------------------------------------------

