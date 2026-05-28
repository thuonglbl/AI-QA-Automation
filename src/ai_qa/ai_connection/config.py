from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for an LLM client."""

    provider: str = Field(
        default="litellm", description="LLM provider (e.g., litellm, openai, anthropic)"
    )
    model_name: str = Field(..., description="The name of the model to use")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")
    base_url: str = Field(default="", description="Base URL for the API (e.g., LiteLLM proxy)")
    api_key: str = Field(default="", description="API key for the provider")
    max_retries: int = Field(
        default=3, ge=0, description="Maximum number of retries for transient errors"
    )
