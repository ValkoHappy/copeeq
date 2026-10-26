from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "anthropic", "compatible"]


class Settings(BaseSettings):
    """Runtime configuration from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="F2W_", extra="ignore", populate_by_name=True
    )

    provider: ProviderName = "openai"
    image_max_side_px: int = 2048

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = "gpt-6.1-sol"
    openai_reasoning_effort: str = "high"
    openai_max_output_tokens: int = 32_000
    openai_image_detail: str = "high"

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "high"
    claude_max_tokens: int = 16_000
    claude_server_fallbacks: bool = True

    # Any OpenAI-compatible Chat Completions server (OpenRouter, Yandex AI Studio, vLLM, Ollama).
    compatible_base_url: str | None = None
    compatible_api_key: SecretStr | None = None
    compatible_model: str | None = None
    compatible_strict: bool = True
    compatible_label: str = "compatible"

    review_max_rounds: int = 2
    preview: Literal["auto", "none"] = "auto"

    yandex_api_key: SecretStr | None = None
    yandex_folder_id: str | None = None
