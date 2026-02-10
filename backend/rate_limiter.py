"""
Shared rate limiter instance.
Used by both run.py (app setup) and routes.py (decorators).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
