# Calls task python functions.
# Wraps input and output from PyStorage objects


import os
import sys
from tasks.common.communicator import CommunicatorOpen, PyStorage

TASK_DIRECTORY = os.path.dirname(__file__)


def fetch_url(text: str):
    slug = "\n\nRETURN_URL_END: "
    i = text.find(slug)
    if i == -1:
        raise ValueError("Return val not found!")
    url = text[i + len(slug) :]

    # comm = CommunicatorOpen(url)
    # storage = PyStorage.loads(comm.recv())
    # val = storage.retrieve()
    # comm.close()

    return url


if __name__ == "__main__":
    if len(sys.argv) != 4 and len(sys.argv) != 3:
        print("Invalid parameters script dir, input_url, output_url (default: auto)")
        sys.exit(-1)

    script = sys.argv[1]
    input_url = sys.argv[2]
    output_url = "auto" if len(sys.argv) < 5 else sys.argv[3]

    comm = CommunicatorOpen(input_url)
    storage = PyStorage.loads(comm.recv())
    inputs = storage.retrieve()

    comm.close()  # direct://fCZHW000000001t0b!Ib

    # The inputs themselves may be more URLs
    final_inputs = []

    for input_url in inputs:
        if isinstance(input_url, str) and input_url.find("://") != -1:
            comm = CommunicatorOpen(input_url)
            storage = PyStorage.loads(comm.recv())
            new_input = storage.retrieve()
            comm.close()
            final_inputs.append(new_input)
        else:
            final_inputs.append(input_url)

    match script:
        case "do_fno":
            import tasks.do_fno as do_fno

            output = do_fno.tk_do_fno(*final_inputs)
        case "do_pcr_partition":
            import tasks.do_pcr as do_pcr

            output = do_pcr.tk_pcr_partition(*final_inputs)
        case "do_pcr":
            import tasks.do_pcr as do_pcr

            output = do_pcr.tk_do_pcr(*final_inputs)
        case "do_pcr_pack":
            import tasks.do_pcr as do_pcr

            output = do_pcr.tk_do_pcr_pack(*final_inputs)
        case "do_pinn":
            import tasks.do_pinn as do_pinn

            output = do_pinn.tk_do_pinn(*final_inputs)
        case "do_sim":
            import tasks.do_simulation as do_simulation

            output = do_simulation.tk_do_simulation(*final_inputs)
        case "get_data":
            import tasks.get_data as get_data

            output = get_data.tk_get_data(*final_inputs)

        case "to_edge":
            import tasks.to_edge as to_edge

            output = to_edge.tk_to_edge(*final_inputs)
        case _:
            print("Invalid script!")
            sys.exit(-2)

    if output_url == "auto":
        output_url = output[0]

    comm = CommunicatorOpen(output_url)
    p = PyStorage(output[1])
    new_url = comm.send(p.serialize())
    comm.close()

    print(f"\n\nRETURN_URL_END: {new_url}")
