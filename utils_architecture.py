import os
import datetime


def verify_config():
    if os.environ.get("INTERIM_DIR") is not None:
        os.makedirs(os.environ.get("INTERIM_DIR"), exist_ok=True)
    else:
        os.environ["INTERIM_DIR"] = "."

    # if len(tf.config.list_physical_devices("GPU")) == 0:
    #     print(tf.config.list_physical_devices("GPU"))
    #     raise ValueError("Missing GPUs")


def get_fdate():
    now = datetime.datetime.now()
    return datetime.datetime.strftime(now, "%m-%d-%Y_%H_%M_%S")
