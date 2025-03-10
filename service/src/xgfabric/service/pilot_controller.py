import radical.pilot as rp


# ------------------------------------------------------------------------------
class PilotController(object):
    """
    A controller class to manage pilot jobs using Radical Pilot.
    """

    # --------------------------------------------------------------------------
    def __init__(self, pmgr, tmgr, resource_description):
        """
        Initialize the PilotController.

        :param pmgr: PilotManager instance
        :param tmgr: TaskManager instance
        :param resource_description: Dictionary describing available system resources.
        """
        self._pmgr = pmgr
        self._tmgr = tmgr
        self._pilots = dict()
        self._resource_description = resource_description

    # --------------------------------------------------------------------------
    def __del__(self):
        """
        Destructor to ensure all pilots are canceled upon deletion of the object.
        """
        for pilot_id in self._pilots:
            self.cancel_pilot(pilot_id)


    # --------------------------------------------------------------------------
    def _submit_pilot(self, nodes=1, runtime=600):
        """
        Submit a new pilot job.

        :param nodes: Number of nodes to allocate for the pilot.
        :param runtime: Duration of the pilot in seconds.
        :return: UID of the submitted pilot.
        """
        pd = rp.PilotDescription()
        pd.resource = self._resource_description.get("resource_type", 'local.localhost')
        pd.nodes = nodes
        pd.runtime = runtime

        pilot = self._pmgr.submit_pilots(pd)
        self._tmgr.add_pilots(pilot)
        self._pilots[pilot.uid] = pilot

        return pilot.uid

    # --------------------------------------------------------------------------
    def cancel_pilot(self, pilot_id):
        """
        Cancel an existing pilot job.

        :param pilot_id: UID of the pilot to be canceled.
        """
        pilot = self._pilots.get(pilot_id)
        if pilot:
            pilot.cancel()
            del self._pilots[pilot_id]

    # --------------------------------------------------------------------------
    def start_initial_pilot(self, expected_workload=None):
        """
        Start an initial pilot job based on available resources and workload demand.

        :param expected_workload: Dictionary describing expected data and workload characteristics.
        :return: UID of the submitted pilot, or None if no pilot is started.
        """
        if self._pilots:
            return  # A pilot is already running, avoid redundant submission.

        if expected_workload and expected_workload.get("size", 0) > 0:
            nodes = min(self._resource_description.get("nodes", 1), max(1, expected_workload["size"] // 10))  # Adjust nodes dynamically
            runtime = min(self._resource_description.get("max_runtime", 600), 600)  # Ensure reasonable runtime
            return self._submit_pilot(nodes=nodes, runtime=runtime)
        elif self._resource_description.get("nodes", 0) > 0:
            return self._submit_pilot(nodes=1, runtime=600)
        else:
            return None

    # --------------------------------------------------------------------------
    def start_pilot(self, data):
        """
        Start a new pilot based on new incoming data.

        Algorithm:
        1. Assess the amount of new data that has not been used in any simulation.
        2. Determine if this data is sufficient to require a new pilot.
        3. Evaluate if the current pilots have enough resources to handle this workload.
        4. If current pilots have sufficient resources, do nothing.
        5. If additional resources are required, start a new pilot with appropriate resource allocation.

        :param data: Dictionary describing new incoming data and its characteristics.
        :return: UID of the submitted pilot if applicable, else None.
        """
        # Determine if new data justifies launching a new pilot
        data_size = data.get("size", 0)
        required_nodes = max(1, data_size // 10)  # Determine needed resources dynamically

        # Check if existing pilots can handle the workload
        total_available_nodes = sum(len(pilot.nodelist)
                                    for pilot in self._pilots.values()
                                    if  pilot.state == rp.PMGR_ACTIVE)
        if total_available_nodes >= required_nodes:
            return None  # No need to start a new pilot

        # Ensure we do not exceed available system resources
        nodes_to_allocate = min(self._resource_description.get("nodes", 1), required_nodes)
        runtime = min(self._resource_description.get("max_runtime", 600), 600)

        return self._submit_pilot(nodes=nodes_to_allocate, runtime=runtime)
