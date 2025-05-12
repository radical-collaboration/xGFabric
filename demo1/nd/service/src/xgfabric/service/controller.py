import radical.pilot as rp


# ------------------------------------------------------------------------------
#
class Controller(object):
    """
    A controller class to manage pilot jobs using Radical Pilot.
    """

    # --------------------------------------------------------------------------
    #
    def __init__(self, cgf):
        """
        Initialize the Controller.

        :param cfg: Dictionary describing expected behavior
        """

        self._session = None  # ensure that `__del__` does not bail

        self._cfg     = cgf

        self._session = rp.Session()
        self._tmgr    = rp.TaskManager(session=self._session)
        self._pmgr    = rp.PilotManager(session=self._session)
        self._descr   = rp.PilotDescription(self._cfg.description)


    # --------------------------------------------------------------------------
    #
    def __del__(self):
        """
        Destructor to ensure all pilots are canceled upon deletion of the object.
        """
        self.close()


    # --------------------------------------------------------------------------
    #
    def close(self):
        """
        Close the session and cancel all pilots.
        """

        if self._session:
            self._session.close()


    # --------------------------------------------------------------------------
    #
    def _get_pilot_size(self, data):
        """
        Based on the expected workload, determine the size of the pilot job.

        :param data: Dictionary describing expected data

        :return: Tuple of (runtime, nodes) for the pilot job.
        """

        # Determine if new data justifies launching a new pilot
        data_size = data.get("size", 0)

        runtime = max(10, data_size // 10)
        nodes   = max( 1, data_size // 10)

        # Check if existing pilots can handle the workload
        # available_nodes = sum(len(pilot.nodelist)
        available_nodes = sum(pilot.description['nodes']
                              for pilot in self._pmgr.get_pilots()
                              if pilot.state == rp.PMGR_ACTIVE)

        # NOTE: this test is always `False` for the first pilot
        if available_nodes >=  nodes:
            # No need to start a new pilot
            return None, None

        return runtime, nodes


    # --------------------------------------------------------------------------
    #
    def _submit_pilot(self, nodes=1, runtime=600):
        """
        Submit a new pilot job.

        :param nodes: Number of nodes to allocate for the pilot.
        :param runtime: Duration of the pilot in seconds.
        :return: UID of the submitted pilot.
        """
        pd = rp.PilotDescription(self._descr.as_dict())
        pd.nodes    = nodes
        pd.runtime  = runtime

        pilot = self._pmgr.submit_pilots(pd)
        self._tmgr.add_pilots(pilot)

        self._pmgr.wait_pilots(pilot.uid, state=[rp.PMGR_ACTIVE] + rp.FINAL)

        if pilot.state != rp.PMGR_ACTIVE:
            raise RuntimeError('Pilot failed to start, state: %s' % pilot.state)

        return pilot.uid


    # --------------------------------------------------------------------------
    #
    def cancel_pilot(self, pilot_id):
        """
        Cancel an existing pilot job.

        :param pilot_id: UID of the pilot to be canceled.
        """
        self._pmgr.cancel_pilots(pilot_id)
        self._pmgr.wait_pilots(pilot_id, state=rp.FINAL)


    # --------------------------------------------------------------------------
    #
    def start_initial_pilot(self, data=None) -> str:
        """
        Start initial pilot job based on available resources and workload demand.

        :param   data: Dictionary describing expected data and workload
                       characteristics.

        :return: UID of the submitted pilot
        """

        if self._pmgr.get_pilots():
            self._log.warning('Pilot already running, no initial pilot needed')
            return

        if data and data.get("size", 0) > 0:

            # Ensure reasonable runtime and resources
            runtime, nodes = self._get_pilot_size(data)

            return self._submit_pilot(nodes=nodes, runtime=runtime)

        else:
            return self._submit_pilot()


    # --------------------------------------------------------------------------
    #
    def start_pilot(self, info) -> str:
        """
        Start a new pilot based on new incoming data.

        Algorithm:
        1. Assess the amount of new data that has not been used in any simulation.
        2. Determine if this data is sufficient to require a new pilot.
        3. Evaluate if the current pilots have enough resources to handle
           this workload.
        4. If current pilots have sufficient resources, do nothing.
        5. If additional resources are required, start a new pilot with
           appropriate resource allocation.

        :param info: Dictionary describing new incoming data and its characteristics.

        :return: UID of the submitted pilot if applicable, else None.
        """

        runtime, nodes = self._get_pilot_size(info.get('data'))

        if nodes:
            return self._submit_pilot(nodes=nodes, runtime=runtime)


    # --------------------------------------------------------------------------
    #
    def run_workload(self, work):

        tasks = self._tmgr.submit_tasks(work)
        self._tmgr.wait_tasks(uids=[t.uid for t in tasks])

        res = list()
        for task in tasks:
            print('%s: [%s][%s]' % (task.state, task.stdout, task.stderr))
            res.append(task.stdout)

        return res


# ------------------------------------------------------------------------------

