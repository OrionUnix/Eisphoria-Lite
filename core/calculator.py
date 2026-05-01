from importlib import import_module

_calculator = import_module("core.France.calculator")

from core.France.calculator import *

__all__ = [name for name in dir(_calculator) if not name.startswith("_")]
