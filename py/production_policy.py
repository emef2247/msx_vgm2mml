"""Scope historical macro selection to ordinary production rendering."""
from contextvars import ContextVar
macro_mode = ContextVar('production_macro_mode', default='current')
