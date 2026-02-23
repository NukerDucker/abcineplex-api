from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    debug: bool = True
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()