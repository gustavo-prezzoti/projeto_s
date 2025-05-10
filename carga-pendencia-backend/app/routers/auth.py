from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional, Dict, Any

from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.auth_service import verify_user, create_access_token, verify_token, register_user, get_current_user_data, is_first_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Valida o token e retorna o usuário atual
    """
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Endpoint para login de usuário
    
    Args:
        form_data: Formulário com username e password
        
    Returns:
        Token de acesso e dados do usuário
    """
    user = verify_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Criar token JWT
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user["id"],
        "username": user["username"]
    }

@router.post("/token", response_model=LoginResponse)
async def login_with_json(login_data: LoginRequest):
    """
    Endpoint para login com JSON em vez de form-data
    
    Args:
        login_data: Dados de login (username e password)
        
    Returns:
        Token de acesso e dados do usuário
    """
    user = verify_user(login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Criar token JWT
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user["id"],
        "username": user["username"]
    }

@router.post("/register", response_model=UserResponse)
async def register(register_data: RegisterRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Endpoint para cadastro de novos usuários
    Apenas usuários autenticados podem cadastrar novos usuários
    
    Args:
        register_data: Dados para cadastro (username, password, nome, email)
        current_user: Usuário atual autenticado
        
    Returns:
        Dados do usuário cadastrado
    """
    # Verificar se o usuário atual tem permissão para cadastrar novos usuários
    user_data = get_current_user_data(current_user.get("user_id"))
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )
    
    # Registrar novo usuário
    new_user = register_user(
        username=register_data.username,
        password=register_data.password,
        nome=register_data.nome,
        email=register_data.email
    )
    
    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível cadastrar o usuário. Username pode já existir.",
        )
    
    return {
        "id": new_user["id"],
        "username": new_user["username"],
        "nome": new_user["nome"],
        "email": new_user["email"],
        "message": "Usuário cadastrado com sucesso"
    }

@router.post("/register-first-user", response_model=UserResponse)
async def register_first_user(register_data: RegisterRequest):
    """
    Endpoint para cadastro do primeiro usuário (admin)
    Este endpoint só funciona se não houver usuários cadastrados no banco
    
    Args:
        register_data: Dados para cadastro (username, password, nome, email)
        
    Returns:
        Dados do usuário cadastrado
    """
    # Verificar se já existem usuários cadastrados
    if not is_first_user():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existem usuários cadastrados no sistema. Use o endpoint /auth/register para cadastrar novos usuários.",
        )
    
    # Registrar primeiro usuário
    new_user = register_user(
        username=register_data.username,
        password=register_data.password,
        nome=register_data.nome,
        email=register_data.email
    )
    
    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível cadastrar o usuário. Username pode já existir.",
        )
    
    return {
        "id": new_user["id"],
        "username": new_user["username"],
        "nome": new_user["nome"],
        "email": new_user["email"],
        "message": "Primeiro usuário (admin) cadastrado com sucesso"
    } 