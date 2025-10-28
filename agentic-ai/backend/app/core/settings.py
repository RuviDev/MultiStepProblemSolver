from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")
    APP_NAME: str = "agentic-ai"
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "agentic_ai"
    ENV: str = "dev"

    # OpenAI
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_REQUEST_TIMEOUT: int = 12

    # Auth / JWT
    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 30

    # --- Component 07 (Insights) ---
    # Vault version to enforce on startup
    INSIGHT_VAULT_VERSION: str = "v2025-10-13"
    # Optional separate model/params (fall back to OPENAI_MODEL if empty)
    INSIGHTS_MODEL: str | None = None
    INSIGHTS_TEMPERATURE: float = 0.2
    INSIGHTS_TOP_P: float = 0.3

settings = Settings()

# convenience accessor for C07 model choice (fallback to main model)
def get_insights_model() -> str:
    return settings.INSIGHTS_MODEL or settings.OPENAI_MODEL