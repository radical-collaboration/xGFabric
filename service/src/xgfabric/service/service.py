
import os
import time
import glob
import random

import threading as mt

import radical.utils as ru
import radical.pilot as rp

from .controller import Controller


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
    def __init__(self, cfg_file: str = None) -> None:

        self._clients = dict()   # client map
        self._ctrl    = None     # controller instance
        self._seen    = list()   # see sequence numbers

        self._cfg = ru.Config(path=cfg_file)

        super().__init__(self._cfg.url)

        self._log = ru.Logger('radical.xgfabric', level='DEBUG_9')


    # --------------------------------------------------------------------------
    def _watch_fs(self):
        '''
        Watch the input dir.  If new data items are found, register them with
        the service.  This is a placeholder for a more sophisticated
        implementation, e.g. using inotify.
        '''

        # register with the service
        uid = self.register_client()

        input_dir  = str(self._cfg.filesystem.input)
        output_dir = str(self._cfg.filesystem.output)

        print('=== starting filesystem watcher: %s' % input_dir)

        try   : ru.rec_makedir(input_dir)
        except: pass

        try   : ru.rec_makedir(output_dir)
        except: pass

        self._watcher_fs_ok.set()

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

                seq_num = random.randint(0, 1000)

                # register new file with the service
                res = self.register_fname(uid, seq_num, fname)

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
    def _parse_cspot_data(self, data):
        '''
        For the given data item, return sequence number, wind speed and
        wind direction
        '''

        elems     = data.split()
        seq_num   = int(elems[-1])
        windspeed = int(elems[0].split(':')[3])
        winddir   = str(elems[0].split(':')[6])

        return seq_num, windspeed, winddir


    # --------------------------------------------------------------------------
    def _watch_cspot(self):
        '''
        constantly (in intervals) pull cspot data and append to log file.  Tail
        that file , extract sequence numbers and data, once changes are
        detected, the *entire* log is passed as input data to data prep script.
        '''

        # register with the service
        uid = self.register_client()

        interval  = int(self._cfg.cspot.interval)
        woof_url  = str(self._cfg.cspot.woof_url)
        woof_path = str(self._cfg.cspot.woof_path)
        data_dir  = str(self._cfg.cspot.data_dir)
        cspot_get = str(self._cfg.cspot.cspot_get)

        print('=== starting cspot watcher: %s/%s' % (woof_url, woof_path))

        logfile = '%s/cspot_data.log' % data_dir

        self._log.info('woof url: %s', woof_url)
        self._log.info('woof path: %s', woof_path)

        try   : ru.rec_makedir(data_dir)
        except: pass

        # read exising log file
        data = list()
        if os.path.exists(logfile):
            with ru.ru_open(logfile, 'r') as fin:
                try:
                    for line in fin:
                        data.append(self._parse_cspot_data(line))
                        self._log.info('old cspot data: %s', data[-1])
                except:
                    self._log.error('failed to parse cspot data: %s', line)

        # append new data to log file
        with open(logfile, 'a') as fout:

            self._watcher_cspot_ok.set()

            # in interval seconds, fetch data from the woof url/path with
            # `cspot-get`
            while True:

                cmd = '%s %s/%s' % (cspot_get, woof_url, woof_path)
                out, err, ret = ru.sh_callout(cmd)

                if ret != 0:
                    self._log.error('cspot-get failed: %s', err)
                    time.sleep(interval)
                    continue

                # allend to logfile
                fout.write(out)

                # evaluate data
                lines = out.strip().split('\n')
                for line in lines:

                    # evaluate data
                    self._log.debug('new cspot data: %s', line)
                    self._log.info('new cspot data: %s', line)
                    data.append(self._parse_cspot_data(line))
                    self._log.info('new cspot data: %s', data[-1])

                    # trigger computation on new sequence numbers
                    if len(data) == 1 or data[-2][0] != data[-1][0]:

                        print('=== new cspot sequence: %s != %s'
                                         % (data[-1][0], data[-2][0]))

                        res = self.register_fname(uid, data[-1][0], logfile)
                        self._log.info('trigger computation: %s', res)

                time.sleep(interval)


    # --------------------------------------------------------------------------
    #
    def __del__(self):

        if self._ctrl:
            self._ctrl.close()


    # --------------------------------------------------------------------------
    #
    def start(self):

        print('=== starting service')

        super().start()

        self._ctrl  = Controller(self._cfg.controller)
      # print('=== submit initial pilot')
      # self._ctrl.start_initial_pilot()

        self.register_request('register_client', self.register_client)
        self.register_request('register_fname',  self.register_fname)

        self._watcher_fs_ok = mt.Event()
        self._watcher_fs    = mt.Thread(target=self._watch_fs)
        self._watcher_fs.daemon = True
        self._watcher_fs.start()

        self._watcher_cspot_ok = mt.Event()
        self._watcher_cspot    = mt.Thread(target=self._watch_cspot)
        self._watcher_cspot.daemon = True
        self._watcher_cspot.start()

        self._watcher_fs_ok.wait(timeout=5.0)
        self._watcher_cspot_ok.wait(timeout=5.0)

        if not self._watcher_fs_ok.is_set():
            raise RuntimeError('could not start fs watcher')

        if not self._watcher_cspot_ok.is_set():
            raise RuntimeError('could not start cspot watcher')

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

        self._log.info('=== client %s registered', client.uid)

        return client.uid


    # --------------------------------------------------------------------------
    #
    def register_fname(self, uid: str, seq_num: str, fname: str) -> str:

        client = self.get_clients(uid)

        with ru.ru_open(fname) as fin:
            data = fin.read()

        print('=== %s: registered %d: %s' % (uid, seq_num, fname))

        if seq_num in self._seen:
            print('=== %s: sequence number already seen' % client.uid)
            return 'sequence %s declined - already seen' % seq_num

        self._seen.append(seq_num)

        client.seq_num = seq_num
        client.fname   = fname
        client.data    = data

        print('=== %s: check resource requirements' % uid)
        pid  = self._ctrl.start_pilot({'data': {'size': len(data)}})

        print('=== %s: submit workload' % uid)
        work = self._get_workload(client)
        res  = self._ctrl.run_workload(work, pid)

        print('=== %s: result: %s' % (uid, res))

        if pid:
            print('=== %s: cancel additional resources' % uid)
            self._ctrl.cancel_pilot(pid)

        return str(res)


    # --------------------------------------------------------------------------
    #
    def _get_workload(self, client: _Client):

        print('=== %s: workload for sequence %s' % (client.uid, client.seq_num))

        env   = self._cfg.workload.environment
        ranks = int(env.get('XGFABRIC_RANKS', 1))

        work = list()
        for idx, template in enumerate(self._cfg.workload.tasks):
            td = rp.TaskDescription(template)
            td.named_env   = 'rp'
            td.sandbox     = 'sandbox'
            td.environment = env

            if 'ranks' in template and not template['ranks']:
                td.ranks = ranks

            if td.uid:
                td.uid = '%s.%s' % (client.seq_num, td.uid)
            else:
                td.uid = '%s.%d' % (client.seq_num, idx)

            print('    === task %s' % td.uid)

            work.append(td)

        return work


# ------------------------------------------------------------------------------

