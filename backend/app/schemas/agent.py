from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=12000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    detailed: bool = False
    language: Literal[
        "en", "hi", "bn", "te", "mr", "ta", "ur", "gu", "kn", "or", "ml", "pa", "as"
    ] = "en"


class AgentQueryResponse(BaseModel):
    query: str
    response: str
