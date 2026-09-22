# Lazy re-export: `from .main import *` pulled TensorFlow/scikit-learn at
# package import, which forced those onto the client and broker just to
# import a submodule (e.g. the investigator wrapper).  PEP 562 defers it
# to attribute access -- `tasks.<pkg>.tk_*` still resolves (on the
# endpoint, where the stack lives; used by wrapper.py), but importing
# `tasks.<pkg>.<submodule>` no longer drags the heavy deps in.
def __getattr__(name):
    from . import main
    return getattr(main, name)
