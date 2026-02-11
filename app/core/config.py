from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    supabase_url: str
    supabase_anon_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    app_name: str = "abcineplex-api"
    debug: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()