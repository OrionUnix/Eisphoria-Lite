from importlib import import_module

_extractor = import_module("core.France.extractor")

from core.France.extractor import *

__all__ = [name for name in dir(_extractor) if not name.startswith("_")]
