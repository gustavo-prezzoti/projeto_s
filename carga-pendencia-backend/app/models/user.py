from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    """Represents a user account"""
    id: Optional[int] = None
    username: str
    password: str
    nome: Optional[str] = None
    email: Optional[str] = None 