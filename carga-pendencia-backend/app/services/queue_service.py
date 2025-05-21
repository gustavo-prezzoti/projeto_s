import pika
import socket
from typing import List, Dict, Any, Optional, Tuple
from app.models.cnpj import CNPJ
import logging
from app.database.config import (
    check_cnpj_exists as supabase_check_cnpj_exists,
    get_all_cnpjs as supabase_get_all_cnpjs,
    insert_cnpj,
    delete_cnpj,
)

# Configure logging
logger = logging.getLogger(__name__)

# Verificar se estamos em ambiente Docker ou local
def is_docker_container_name_resolvable(container_name):
    try:
        socket.gethostbyname(container_name)
        return True
    except socket.gaierror:
        return False

# Determinar os hosts baseados no ambiente
RABBITMQ_HOST = "rabbitmq-cnpj" if is_docker_container_name_resolvable("rabbitmq-cnpj") else "localhost"

print(f"[Queue Service] Usando RabbitMQ em: {RABBITMQ_HOST}")

def check_cnpj_exists(cnpj: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a CNPJ already exists in the database
    
    Args:
        cnpj: The CNPJ to check
        
    Returns:
        Tuple of (exists, record) where record contains the DB data if exists is True
    """
    return supabase_check_cnpj_exists(cnpj)

def get_all_cnpjs(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all CNPJs from the database, optionally filtered by user_id
    
    Args:
        user_id: Optional user ID to filter by
        
    Returns:
        List of all CNPJ records for the specified user or all records if no user specified
    """
    return supabase_get_all_cnpjs(user_id)

def send_to_queue_and_db(cnpj_obj, user_id: Optional[int] = None):
    """
    Send a CNPJ to the queue and save it to the database
    
    Args:
        cnpj_obj: CNPJ object to process
        user_id: Optional user ID to associate with this CNPJ
    """
    connection = None
    channel = None
    
    try:
        # Prepara os dados do CNPJ para inserção
        cnpj_data = {
            "cnpj": cnpj_obj.cnpj,
            "razao_social": cnpj_obj.razao_social or "",
            "municipio": cnpj_obj.municipio or "",
            "status": "pendente"
        }
        
        if user_id is not None:
            cnpj_data["user_id"] = user_id
        
        # Insere no Supabase
        fila_id = insert_cnpj(cnpj_data)
        
        if not fila_id:
            raise Exception("Falha ao inserir CNPJ no banco de dados")

        # Envia para o RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='fila_cnpj')
        channel.basic_publish(
            exchange='',
            routing_key='fila_cnpj',
            body=str(fila_id)
        )
        
        print(f"CNPJ added to queue: {cnpj_obj.cnpj}, ID: {fila_id}, User ID: {user_id}")
        return fila_id
    except Exception as e:
        logger.error(f"Error in send_to_queue_and_db: {str(e)}")
        print(f"Error in send_to_queue_and_db: {str(e)}")
        raise
    finally:
        if connection and connection.is_open:
            connection.close()

def delete_from_queue_by_id(fila_id: int, user_id: Optional[int] = None) -> bool:
    """
    Remove um CNPJ da fila pelo ID
    
    Args:
        fila_id: ID do registro na fila
        user_id: ID do usuário (opcional para verificação de permissão)
        
    Returns:
        True se o registro foi removido com sucesso, False caso contrário
    """
    connection = None
    channel = None
    
    try:
        # Primeiro verifica se o registro existe e pertence ao usuário (feito pelo serviço de Supabase)
        exists = delete_cnpj(fila_id, user_id)
        
        if not exists:
            return False
        
        # Se o registro existe e foi excluído com sucesso, adiciona o ID à fila de ignorados do RabbitMQ
        try:
            # Conecta ao RabbitMQ para criar uma fila de ignorados se não existir
            connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
            channel = connection.channel()
            channel.queue_declare(queue='fila_cnpj_ignorados', durable=True)
            
            # Adiciona o ID à fila de ignorados
            channel.basic_publish(
                exchange='',
                routing_key='fila_cnpj_ignorados',
                body=str(fila_id),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Mensagem persistente
                )
            )
            
            logger.info(f"ID {fila_id} adicionado à fila de ignorados")
        except Exception as e:
            logger.error(f"Erro ao adicionar ID {fila_id} à fila de ignorados: {str(e)}")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar CNPJ da fila: {str(e)}")
        return False
    finally:
        if connection and connection.is_open:
            connection.close() 