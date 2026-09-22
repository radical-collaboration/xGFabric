# Service-mode (DTaaS / ORBIT) variant of the xGFabric twin.
#
# Same graph and the same model-selection story as ../twin.py -- a wind
# sensor feeds a field agent whose three competing surrogates are ranked
# by profiler-predicted Pi runtime -- but the components here are
# service-safe: they ship to the broker by value, run their tasks on a
# rhapsody endpoint, and fake the physics (as twin.py already does for
# the sensor and the simulation).  The real FNO/PINN/PCR training stacks
# stay in ../tasks and are NOT imported here.
