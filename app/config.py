from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    supabase_url: str
    supabase_publishable_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    app_name: str = "ABCineplex API"
    debug: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()