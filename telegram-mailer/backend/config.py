from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import field_validator

class Settings(BaseSettings):
    bot_token: str
    superadmin_id: int
    database_url: str
    redis_url: str
    encryption_key: str
    default_api_id: Optional[int] = None
    default_api_hash: Optional[str] = None
    max_accounts: int = 100
    default_message_interval: int = 30
    default_cycle_interval: int = 300
    log_level: str = "INFO"

    @field_validator('default_api_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return int(v)

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
