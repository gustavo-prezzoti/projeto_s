import jwt
from datetime import datetime, timedelta
import os
import hashlib
from typing import Optional, Dict, Any

from app.database.config import (
    verify_user as supabase_verify_user,
    register_user as supabase_register_user,
    get_user_by_id,
    count_users
)

# Definir chave secreta para JWT
# Em produção, isso deve ser armazenado em uma variável de ambiente
SECRET_KEY = "8133d9a97df928e1d18cd20c5f4ae569b4d4c39d672d524fb4025a9e32f7ddfa"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Cria um token JWT com os dados fornecidos
    
    Args:
        data: Dados a serem codificados no token
        expires_delta: Tempo de expiração do token
        
    Returns:
        Token JWT assinado
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifica e decodifica um token JWT
    
    Args:
        token: Token JWT a ser verificado
        
    Returns:
        Dados decodificados do token ou None se o token for inválido
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

def hash_password(password: str) -> str:
    """
    Cria um hash da senha usando SHA-256
    
    Args:
        password: Senha em texto puro
        
    Returns:
        Hash da senha
    """
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verifica as credenciais do usuário
    
    Args:
        username: Nome de usuário
        password: Senha em texto puro
        
    Returns:
        Dados do usuário se as credenciais forem válidas, None caso contrário
    """
    try:
        # Hash da senha
        password_hash = hash_password(password)
        
        # Verificar usuário no Supabase
        return supabase_verify_user(username, password_hash)
    except Exception as e:
        print(f"Erro ao verificar usuário: {str(e)}")
        return None

def register_user(username: str, password: str, nome: Optional[str] = None, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Registra um novo usuário no banco de dados
    
    Args:
        username: Nome de usuário
        password: Senha em texto puro
        nome: Nome completo (opcional)
        email: E-mail (opcional)
        
    Returns:
        Dados do usuário registrado ou None em caso de erro
    """
    try:
        # Hash da senha
        hashed_password = hash_password(password)
        
        # Preparar dados do usuário
        user_data = {
            "username": username,
            "password": hashed_password,
            "nome": nome,
            "email": email
        }
        
        # Registrar usuário no Supabase
        return supabase_register_user(user_data)
    except Exception as e:
        print(f"Erro ao registrar usuário: {str(e)}")
        return None

def get_current_user_data(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtém os dados do usuário pelo ID
    
    Args:
        user_id: ID do usuário
        
    Returns:
        Dados do usuário ou None se não encontrado
    """
    try:
        return get_user_by_id(user_id)
    except Exception as e:
        print(f"Erro ao obter dados do usuário: {str(e)}")
        return None

def is_first_user() -> bool:
    """
    Verifica se não existem usuários cadastrados no banco
    
    Returns:
        True se não existem usuários, False caso contrário
    """
    try:
        # Contar usuários no Supabase
        user_count = count_users()
        
        # Se não houver usuários, é o primeiro
        return user_count == 0
    except Exception as e:
        print(f"Erro ao verificar se é primeiro usuário: {str(e)}")
        # Em caso de erro, assume que não é o primeiro usuário (segurança)
        return False 