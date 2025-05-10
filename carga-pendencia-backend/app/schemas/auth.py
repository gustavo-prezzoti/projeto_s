from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    """Login request schema"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Login response schema"""
    access_token: str
    token_type: str
    user_id: int
    username: str

class RegisterRequest(BaseModel):
    """Register request schema"""
    username: str
    password: str
    nome: Optional[str] = None
    email: Optional[str] = None

class UserResponse(BaseModel):
    """User response schema"""
    id: int
    username: str
    nome: Optional[str] = None
    email: Optional[str] = None
    message: str 