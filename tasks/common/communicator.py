from typing import cast

from .pyspot.pyspot.senspot import (
    WooFItem,
    FileWooFLocations,
    FileWooFItem,
    FileWooF,
    WooF,
)
from dragon.data import DDict
import cloudpickle
import base64

# The data structure / format of the data to store between tasks


class PyStorage:
    def __init__(self, data=None):
        self.object = data

    def store(self, object):
        self.object = object

    def retrieve(self):
        return self.object

    def serialize(self):
        return cloudpickle.dumps(self.object)

    @classmethod
    def loads(cls, bindata):
        out = cls()
        out.store(cloudpickle.loads(bindata))
        return out


# The actual transport agent to transfer data between tasks / machines


class AbstractCommunicator:
    def __init__(self, url):
        self.url = url

    def setup(self):
        pass

    def send(self, data: bytes) -> str:
        raise NotImplementedError

    def recv(self) -> bytes:
        raise NotImplementedError

    def close(self):
        pass


class DirectCommunicator(AbstractCommunicator):
    scheme = "direct://"

    def __init__(self, url):
        super().__init__(url)
        text = url.replace(DirectCommunicator.scheme, "")
        raw_bytes = base64.b85decode(text)
        self.data = raw_bytes

    def send(self, data: bytes) -> str:
        if len(data) > 10 * 1024:
            raise ValueError("Too big for direct comm!")
        raw_text = base64.b85encode(data).decode("utf-8")
        return f"{DirectCommunicator.scheme}{raw_text}"

    def recv(self) -> bytes:
        return self.data


class FileWooFCommunicator(AbstractCommunicator):
    scheme = "fwoof://"

    def __init__(self, url: str, bin_path=None):
        # print(f"URL: {url}")
        super().__init__(url)
        url = url.replace(FileWooFCommunicator.scheme, "woof://")
        version_to_get = -1
        qmark = url.find("?")
        if qmark != -1:
            ending = url[qmark:]
            version_to_get = int(ending.replace("?v=", ""))
            self.woof_url = url[:qmark]
        else:
            self.woof_url = url

        self.url = "f" + self.woof_url

        self.version = version_to_get

        self.fwoof = FileWooF(self.woof_url, bin_path)

    def send(self, data: bytes):
        version, end_seq_no = self.fwoof.put(data)
        return self.url + f"?v={version}"

    def recv(self) -> bytes:
        item = self.fwoof.get(self.version)
        return item.data  # type: ignore


class WooFCommunicator(AbstractCommunicator):
    scheme = "woof://"

    def __init__(self, url, bin_path=None, is_jumbo=False):
        super().__init__(url)
        self.woof = WooF(self.url, bin_path, is_jumbo=is_jumbo)

    def send(self, data: bytes):
        self.woof.WooFPut(data)
        return self.url  # Adjust later to include version number

    def recv(self) -> bytes:
        item = self.woof.WooFGet(bytes)
        return item.data


class FileSystemCommunicator(AbstractCommunicator):
    scheme = "file://"

    def __init__(self, url):
        super().__init__(url)
        minus_scheme = self.url[len(FileSystemCommunicator.scheme) :]
        self.raw_url: str = minus_scheme

        # location. Convert "NERSC" to /
        tokens = self.raw_url.split("/", 1)
        location = tokens[0]
        path = tokens[1]
        self.raw_url = "/" + path

    def send(self, data: bytes):
        with open(self.raw_url, "wb") as f:
            f.write(data)
        return self.url

    def recv(self) -> bytes:
        f = open(self.raw_url, "rb")
        out = f.read()
        f.close()
        return out


class DDictCommunicator(AbstractCommunicator):
    scheme = "ddict://"

    def __init__(self, ddict_object: DDict | str):
        if isinstance(ddict_object, DDict):
            self.d = ddict_object
        else:
            # remove location
            tokens = ddict_object.split("/")
            ddict = tokens[-1]
            self.d = DDict.attach(ddict)

    # DDicts are merely transferred by the reference. The dragon runtime figures
    # out the rest

    def get_url(self, location):
        return f"{DDictCommunicator.scheme}{location}/{self.d.serialize()}"

    def send(self, d: DDict):
        # DDict does this behind the scenes. You just give the URL
        return self.d

    def recv(self) -> DDict:  # type: ignore
        return self.d

    def close(self):
        return self.d.detach()


def CommunicatorOpen(url) -> AbstractCommunicator:
    if isinstance(url, DDict):
        return DDictCommunicator(url)

    scheme_index = url.find("://")
    if scheme_index == -1:
        raise ValueError(f"No scheme found. Received url: {url}")

    scheme = url[: scheme_index + 3]

    match scheme:
        case FileWooFCommunicator.scheme:
            return FileWooFCommunicator(url)
        case WooFCommunicator.scheme:
            return WooFCommunicator(url)
        case FileSystemCommunicator.scheme:
            return FileSystemCommunicator(url)
        case DDictCommunicator.scheme:
            return DDictCommunicator(url)
        case DirectCommunicator.scheme:
            return DirectCommunicator(url)
        case _:
            raise ValueError(f"Unknown scheme {scheme}")


if __name__ == "__main__":

    # Communication test

    # FileWooF Communication

    url = "fwoof://169.231.229.75/sharedfs/ucsb-data/test-senspot-file.woof"
    comm = CommunicatorOpen(url)
    comm.send(b"ABC")
    print(comm.recv())
    comm.close()

    # WooF Communication

    url = "woof://169.231.229.75/sharedfs/ucsb-data/test-senspot.woof"
    comm = CommunicatorOpen(url)
    comm.send(b"ABC")
    print(comm.recv())
    comm.close()

    # FileSystemCommunicator

    url = "file://nersc.local/global/homes/b/bcarter/pppl/repos/xGFabric/tasks/common/test.txt"
    comm = CommunicatorOpen(url)
    comm.send(b"ABC")
    print(comm.recv())
    comm.close()

    # DDict Communicator
    d = DDict()
    location = "nersc"
    dcomm = DDictCommunicator(d)
    url = dcomm.get_url(location)
    print(url)

    d["test"] = b"ABC"

    # from get_url
    comm = CommunicatorOpen(url)
    d2 = cast(DDict, comm.recv())
    print(d2["test"])
    comm.close()

    # from reference directly
    comm = CommunicatorOpen(d)
    d2 = cast(DDict, comm.recv())
    print(d2["test"])
    comm.close()

    # Data Storage Test

    url = "fwoof://169.231.229.75/sharedfs/ucsb-data/test-senspot-file.woof"
    comm = CommunicatorOpen(url)
    data = PyStorage()
    data.store((1, 2, 3, 4))
    comm.send(data.serialize())
    data2 = PyStorage.loads(comm.recv())
    print(data2.retrieve())
    comm.close()

    url = "woof://169.231.229.75/sharedfs/ucsb-data/test-senspot.woof"
    comm = CommunicatorOpen(url)
    data = PyStorage()
    data.store((1, 2, 3, 4))
    comm.send(data.serialize())
    data2 = PyStorage.loads(comm.recv())
    print(data2.retrieve())
    comm.close()

    url = "file://nersc.local/global/homes/b/bcarter/pppl/repos/xGFabric/tasks/common/test.txt"
    comm = CommunicatorOpen(url)
    data = PyStorage()
    data.store((1, 2, 3, 4))
    comm.send(data.serialize())
    data2 = PyStorage.loads(comm.recv())
    print(data2.retrieve())
    comm.close()

    d = DDict()
    location = "nersc"
    dcomm = DDictCommunicator(d)
    url = dcomm.get_url(location)
    print(url)

    d["test"] = (1, 2, 3, 4)

    # from get_url
    comm = CommunicatorOpen(url)
    d2 = cast(DDict, comm.recv())
    print(d2["test"])
    comm.close()
