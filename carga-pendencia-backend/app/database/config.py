"""
Configuração centralizada para conexões com Supabase e PostgreSQL
"""
import os
from typing import Dict, Any, Optional, List
import logging
from supabase import create_client, Client

# Configure logging
logger = logging.getLogger(__name__)

# Credenciais do Supabase
SUPABASE_URL = "https://tvcnimbrqzimfggfhqst.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR2Y25pbWJycXppbWZnZ2ZocXN0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NzgzNDYwMywiZXhwIjoyMDYzNDEwNjAzfQ.PtQQdSO_FuZw0eyhfMGB1YbcWvfxy82cFRsq_uauq2o"

# Informações do PostgreSQL
POSTGRES_HOST = "aws-0-sa-east-1.pooler.supabase.com"
POSTGRES_PORT = 5432
POSTGRES_PORT_POOLING = 6543
POSTGRES_DB = "postgres"
POSTGRES_USER = f"postgres.{SUPABASE_URL.split('//')[1].split('.')[0]}"  # Extrai o ID do projeto da URL
POSTGRES_PASSWORD = SUPABASE_KEY  # Mesma chave do Supabase

# Singleton para o cliente Supabase
_supabase_client = None

def get_supabase_client() -> Client:
    """
    Obtém uma instância única do cliente Supabase
    
    Returns:
        Client: Cliente Supabase inicializado
    """
    global _supabase_client
    if _supabase_client is None:
        try:
            # Usar uma inicialização simples sem argumentos extras que podem causar erro
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Cliente Supabase inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao inicializar cliente Supabase: {e}")
            raise
    return _supabase_client

# Funções para operações comuns no banco de dados

def check_cnpj_exists(cnpj: str) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verifica se um CNPJ já existe no banco de dados
    
    Args:
        cnpj: CNPJ a ser verificado
        
    Returns:
        Tupla (existe, registro) onde registro contém os dados do banco se existe for True
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fila_cnpj").select("*").eq("cnpj", cnpj).execute()
        
        if response.data and len(response.data) > 0:
            return True, response.data[0]
        return False, None
    except Exception as e:
        logger.error(f"Erro ao verificar CNPJ {cnpj}: {e}")
        return False, None

def get_all_cnpjs(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Obtém todos os CNPJs do banco de dados, opcionalmente filtrados por user_id
    
    Args:
        user_id: ID do usuário opcional para filtrar
        
    Returns:
        Lista de todos os registros de CNPJ do usuário especificado ou todos os registros se nenhum usuário for especificado
    """
    try:
        supabase = get_supabase_client()
        query = supabase.table("fila_cnpj").select("*")
        
        if user_id is not None:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        logger.error(f"Erro ao obter CNPJs: {e}")
        return []

def insert_cnpj(cnpj_data: Dict[str, Any]) -> Optional[int]:
    """
    Insere um novo registro de CNPJ no banco de dados
    
    Args:
        cnpj_data: Dicionário com os dados do CNPJ
        
    Returns:
        ID do registro inserido ou None em caso de erro
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fila_cnpj").insert(cnpj_data).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0].get("id")
        return None
    except Exception as e:
        logger.error(f"Erro ao inserir CNPJ: {e}")
        return None

def delete_cnpj(fila_id: int, user_id: Optional[int] = None) -> bool:
    """
    Remove um registro de CNPJ pelo ID
    
    Args:
        fila_id: ID do registro na fila
        user_id: ID do usuário opcional para verificação de permissão
        
    Returns:
        True se o registro foi removido com sucesso, False caso contrário
    """
    try:
        supabase = get_supabase_client()
        
        # Primeiro, verifica se o registro existe e pertence ao usuário
        query = supabase.table("fila_cnpj").select("id").eq("id", fila_id)
        
        if user_id is not None:
            # Se user_id for fornecido, adiciona a condição
            # Considera tanto registros com esse user_id quanto registros sem user_id
            query = query.or_(f"user_id.eq.{user_id},user_id.is.null")
            
        existing = query.execute()
        
        if not existing.data or len(existing.data) == 0:
            logger.warning(f"CNPJ com ID {fila_id} não encontrado ou usuário {user_id} sem permissão")
            return False
            
        # Remove o registro
        response = supabase.table("fila_cnpj").delete().eq("id", fila_id).execute()
        
        if response.data and len(response.data) > 0:
            logger.info(f"CNPJ com ID {fila_id} removido com sucesso")
            return True
        
        logger.warning(f"Nenhum CNPJ foi removido para o ID {fila_id}")
        return False
    except Exception as e:
        logger.error(f"Erro ao excluir CNPJ com ID {fila_id}: {e}")
        return False

def update_queue_item(fila_id: int, data: Dict[str, Any]) -> bool:
    """
    Atualiza um item da fila pelo ID
    
    Args:
        fila_id: ID do registro na fila
        data: Dados a serem atualizados
        
    Returns:
        True se o registro foi atualizado com sucesso, False caso contrário
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fila_cnpj").update(data).eq("id", fila_id).execute()
        
        if response.data and len(response.data) > 0:
            logger.info(f"CNPJ com ID {fila_id} atualizado com sucesso")
            return True
        
        logger.warning(f"Nenhum CNPJ foi atualizado para o ID {fila_id}")
        return False
    except Exception as e:
        logger.error(f"Erro ao atualizar CNPJ com ID {fila_id}: {e}")
        return False

def verify_user(username: str, password_hash: str) -> Optional[Dict[str, Any]]:
    """
    Verifica as credenciais do usuário
    
    Args:
        username: Nome de usuário
        password_hash: Hash da senha
        
    Returns:
        Dados do usuário se as credenciais forem válidas, None caso contrário
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("users").select("*").eq("username", username).eq("password", password_hash).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao verificar usuário {username}: {e}")
        return None

def register_user(user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Registra um novo usuário no banco de dados
    
    Args:
        user_data: Dicionário com os dados do usuário
        
    Returns:
        Dados do usuário registrado ou None em caso de erro
    """
    try:
        supabase = get_supabase_client()
        
        # Verifica se já existe um usuário com esse username
        existing = supabase.table("users").select("id").eq("username", user_data["username"]).execute()
        
        if existing.data and len(existing.data) > 0:
            logger.warning(f"Usuário {user_data['username']} já existe")
            return None
            
        # Insere o novo usuário
        response = supabase.table("users").insert(user_data).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao registrar usuário: {e}")
        return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtém os dados do usuário pelo ID
    
    Args:
        user_id: ID do usuário
        
    Returns:
        Dados do usuário ou None se não encontrado
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao obter usuário com ID {user_id}: {e}")
        return None

def count_users() -> int:
    """
    Conta o número de usuários no banco
    
    Returns:
        Número de usuários
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("users").select("count", count="exact").execute()
        
        if hasattr(response, "count"):
            return response.count
        return 0
    except Exception as e:
        logger.error(f"Erro ao contar usuários: {e}")
        return 0 