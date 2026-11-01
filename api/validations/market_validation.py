"""Corps de requete du marche (assistant conversationnel sur une analyse)."""

from typing import List, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    # L'historique est tronque aux 20 derniers messages par le service ; la
    # borne ici refuse d'emblee un corps demesure.
    messages: List[ChatMessage] = Field(max_length=100)
