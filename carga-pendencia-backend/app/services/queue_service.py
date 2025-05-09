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

def get_all_cnpjs() -> List[Dict[str, Any]]:
    """
    Get all CNPJs from the database
    
    Returns:
        List of all CNPJ records
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

def send_to_queue_and_db(cnpj_obj):
    """
    Send a CNPJ to the queue and save it to the database
    
    Args:
        cnpj_obj: CNPJ object to process
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
        
        print(f"CNPJ added to queue: {cnpj_obj.cnpj}, ID: {fila_id}")
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