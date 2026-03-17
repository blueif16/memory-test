"""
Shared service-layer utilities.
"""
from functools import lru_cache

from supabase import create_client, Client
from app.config import config


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Shared Supabase client instance."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
