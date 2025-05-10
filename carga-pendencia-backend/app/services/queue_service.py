import pika
import mysql.connector
import socket
from typing import List, Dict, Any, Optional, Tuple
from app.models.cnpj import CNPJ
import logging

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
MYSQL_HOST = "mysql-cnpj" if is_docker_container_name_resolvable("mysql-cnpj") else "localhost"
RABBITMQ_HOST = "rabbitmq-cnpj" if is_docker_container_name_resolvable("rabbitmq-cnpj") else "localhost"

print(f"[Queue Service] Usando MySQL em: {MYSQL_HOST}")
print(f"[Queue Service] Usando RabbitMQ em: {RABBITMQ_HOST}")

def check_cnpj_exists(cnpj: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a CNPJ already exists in the database
    
    Args:
        cnpj: The CNPJ to check
        
    Returns:
        Tuple of (exists, record) where record contains the DB data if exists is True
    """
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM fila_cnpj WHERE cnpj = %s ORDER BY data_criacao DESC LIMIT 1",
            (cnpj,)
        )
        result = cursor.fetchone()
        
        if result:
            # Convert any non-serializable types to strings
            for key, value in result.items():
                if key in ['data_criacao', 'data_atualizacao'] and value is not None:
                    result[key] = value.isoformat()
            return True, result
        return False, None
    except Exception as e:
        logger.error(f"Error checking if CNPJ exists: {str(e)}")
        print(f"Database error in check_cnpj_exists: {str(e)}")
        # Return False on error to avoid blocking the process
        return False, None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_all_cnpjs(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all CNPJs from the database, optionally filtered by user_id
    
    Args:
        user_id: Optional user ID to filter by
        
    Returns:
        List of all CNPJ records for the specified user or all records if no user specified
    """
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)
        
        if user_id is not None:
            cursor.execute("SELECT * FROM fila_cnpj WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT * FROM fila_cnpj")
            
        result = cursor.fetchall()
        
        # Convert any non-serializable types to strings
        for item in result:
            for key, value in item.items():
                if key in ['data_criacao', 'data_atualizacao'] and value is not None:
                    item[key] = value.isoformat()
        
        return result
    except Exception as e:
        logger.error(f"Error getting all CNPJs: {str(e)}")
        print(f"Database error in get_all_cnpjs: {str(e)}")
        # Return empty list on error to avoid blocking the process
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_to_queue_and_db(cnpj_obj, user_id: Optional[int] = None):
    """
    Send a CNPJ to the queue and save it to the database
    
    Args:
        cnpj_obj: CNPJ object to process
        user_id: Optional user ID to associate with this CNPJ
    """
    conn = None
    cursor = None
    connection = None
    channel = None
    
    try:
        # Grava no banco como pendente
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",  # Atualizado para senha do Docker
            database="relatorio_pendencia"
        )
        cursor = conn.cursor()
        
        if user_id is not None:
            cursor.execute(
                "INSERT INTO fila_cnpj (cnpj, razao_social, municipio, status, user_id) VALUES (%s, %s, %s, %s, %s)",
                (cnpj_obj.cnpj, cnpj_obj.razao_social, cnpj_obj.municipio, "pendente", user_id)
            )
        else:
            cursor.execute(
                "INSERT INTO fila_cnpj (cnpj, razao_social, municipio, status) VALUES (%s, %s, %s, %s)",
                (cnpj_obj.cnpj, cnpj_obj.razao_social, cnpj_obj.municipio, "pendente")
            )
        
        conn.commit()
        fila_id = cursor.lastrowid

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
    except mysql.connector.Error as db_error:
        logger.error(f"Database error in send_to_queue_and_db: {str(db_error)}")
        print(f"Database error in send_to_queue_and_db: {str(db_error)}")
        raise
    except pika.exceptions.AMQPError as rabbitmq_error:
        logger.error(f"RabbitMQ error in send_to_queue_and_db: {str(rabbitmq_error)}")
        print(f"RabbitMQ error in send_to_queue_and_db: {str(rabbitmq_error)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_to_queue_and_db: {str(e)}")
        print(f"Unexpected error in send_to_queue_and_db: {str(e)}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
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
    conn = None
    cursor = None
    connection = None
    channel = None
    
    try:
        # Primeiro, obtém os detalhes do registro para verificar
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)
        
        # Se user_id é fornecido, verifica se o registro pertence a este usuário
        if user_id is not None:
            cursor.execute(
                "SELECT * FROM fila_cnpj WHERE id = %s AND user_id = %s",
                (fila_id, user_id)
            )
        else:
            cursor.execute("SELECT * FROM fila_cnpj WHERE id = %s", (fila_id,))
            
        registro = cursor.fetchone()
        
        if not registro:
            # Registro não encontrado ou não pertence ao usuário
            return False
        
        # Se o status for 'pendente', tenta remover da fila do RabbitMQ também
        # Nota: Isso é complexo pois RabbitMQ não permite remover mensagens específicas facilmente
        # A alternativa é criar uma lista de IDs ignorados no worker
        if registro['status'] == 'pendente' or registro['status'] == 'processando':
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
        
        # Agora remove o registro do banco de dados
        cursor.execute("DELETE FROM fila_cnpj WHERE id = %s", (fila_id,))
        conn.commit()
        
        affected_rows = cursor.rowcount
        logger.info(f"ID {fila_id} removido do banco de dados. Linhas afetadas: {affected_rows}")
        
        return affected_rows > 0
    except Exception as e:
        logger.error(f"Erro ao deletar CNPJ da fila: {str(e)}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        if connection and connection.is_open:
            connection.close() 