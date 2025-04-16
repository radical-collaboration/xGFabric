
import os
import time
import glob

import threading as mt

import radical.utils as ru
import radical.pilot as rp

from .pilot_controller import PilotController

watcher_cfg = {'data' : {'input' : './INPUT/',
                         'output': './OUTPUT/'}}


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


    # --------------------------------------------------------------------------
    def _watcher_service(self):
        '''
        Watch the input dir.  If new data items are found, register them with
        the service.  This is a placeholder for a more sophisticated
        implementation, e.g. using inotify.
        '''

        print('watcher started')

        cfg = ru.Config(watcher_cfg)

        input_dir  = str(cfg.data.input)
        output_dir = str(cfg.data.output)

        ru.rec_makedir(input_dir)
        ru.rec_makedir(output_dir)

        while True:

            # check for new files in the input dir
            files = glob.glob('%s/*' % input_dir)

            for fname in files:

                # ignore done markers
                if fname.endswith('.done'):
                    continue

                # check for done marker
                if os.path.exists('%s.done' % fname):
                    continue

                print('new input data: %s' % fname)

                # register new file with the service
                uid = self.register_client()
                res = self.register_fname(uid, fname)

                tgt = '%s/%s.out' % (output_dir, os.path.basename(fname))
                with open(tgt, 'w') as fout:
                    fout.write(res)

                # create done marker
                with open('%s.done' % fname, 'w') as fout:
                    fout.write('done')

                print('output data: %s' % tgt)

            time.sleep(1)


    # --------------------------------------------------------------------------
    #
    def __del__(self):

        if self._session:
            self._session.close()


    # --------------------------------------------------------------------------
    #
    def start(self):

        super().start()

        self._session = rp.Session()
        self._tmgr    = rp.TaskManager(session=self._session)
        self._pmgr    = rp.PilotManager(session=self._session)

        self._p_ctrl  = PilotController(self._pmgr, self._tmgr,
                                        {'resource_type': 'local.localhost',
                                         'nodes'        : 8,
                                         'max_runtime'  : 600})
        self._p_ctrl.start_initial_pilot()

        self.register_request('register_client', self.register_client)
        self.register_request('register_fname',  self.register_fname)

        self._watcher = mt.Thread(target=self._watcher_service)
        self._watcher.daemon = True
        self._watcher.start()

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

        pid = self._p_ctrl.start_pilot({'data': data})

        tds = list()
        td  = rp.TaskDescription()
        td.executable = '/bin/wc'
        td.arguments  = ['DATA:', data]
        tds.append(td)

        tasks = self._tmgr.submit_tasks(tds)
        self._tmgr.wait_tasks()

        res = list()
        for task in tasks:
            res.append(task.stdout)

        self._log.info('client %s result: %s', uid, res)

        self._p_ctrl.cancel_pilot(pid)

        return str(res)


# ------------------------------------------------------------------------------

