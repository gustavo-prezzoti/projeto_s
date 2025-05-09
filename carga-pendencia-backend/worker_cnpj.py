import pika
import mysql.connector
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.models.cnpj import CNPJ
from app.services.cnpj_service import CNPJService
import os
import glob
import subprocess
import tempfile
import socket
import unicodedata
import re
import traceback
import time
import random
import argparse
import sys

# Limitar a quantidade de workers simultâneos por instância do worker
# Reduzir de 10 para 3 para evitar sobrecarga ao executar múltiplas instâncias
executor = ThreadPoolExecutor(max_workers=3)

# Função para calcular tempos de espera dinâmicos baseados no tamanho do batch
def calculate_wait_time(batchsize):
    """
    Calcula tempos de espera dinâmicos baseados no tamanho do batch
    
    Args:
        batchsize: Tamanho do batch configurado
        
    Returns:
        Dicionário com os diferentes tempos de espera
    """
    # Valores base
    if batchsize <= 5:
        base_wait = 20
    elif batchsize <= 20:
        base_wait = 35
    elif batchsize <= 50:
        base_wait = 40
    else:
        base_wait = 90
    
    # Calcula diferentes tempos baseados no tempo base
    return {
        "page_load": base_wait,                    # Tempo para carregar página
        "after_click": base_wait * 0.5,            # Tempo após cliques
        "form_fill": max(5, base_wait * 0.3),      # Tempo para preenchimento de formulário
        "element_wait": max(10, base_wait * 0.7),  # Timeout para esperar elementos
        "between_tasks": max(3, base_wait * 0.2)   # Tempo entre tarefas do batch
    }

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

# Variável global para armazenar tempos de espera
WAIT_TIMES = calculate_wait_time(20)  # Valor padrão inicial

print(f"Usando MySQL em: {MYSQL_HOST}")
print(f"Usando RabbitMQ em: {RABBITMQ_HOST}")
print(f"Tempos de espera iniciais: {WAIT_TIMES}")

# Configuração de conexão do MySQL com timeout e retry
def get_db_connection():
    retry_attempts = 3
    for attempt in range(retry_attempts):
        try:
            return mysql.connector.connect(
                host=MYSQL_HOST,
                user="root",
                password="root",
                database="relatorio_pendencia",
                connection_timeout=30,
                autocommit=False
            )
        except mysql.connector.Error as err:
            if attempt < retry_attempts - 1:
                print(f"Erro ao conectar ao MySQL (tentativa {attempt+1}): {err}")
                time.sleep(random.uniform(1, 3))  # Backoff aleatório
            else:
                raise

def verificar_tarefas_pendentes_lote(limit=50):
    print(f"[LOG] Chamando verificar_tarefas_pendentes_lote com limit={limit}")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        print("[LOG] Conexão com o banco obtida com sucesso.")
        cursor.execute("SELECT id FROM fila_cnpj WHERE status = 'pendente' LIMIT %s", (limit,))
        tarefas = cursor.fetchall()
        print(f"[LOG] Resultado do SELECT pendentes: {tarefas}")
        if not tarefas:
            print("[LOG] Nenhuma tarefa pendente encontrada.")
            return []
        ids = [t['id'] for t in tarefas]
        print(f"[LOG] IDs encontrados: {ids}")
        if ids:
            id_placeholders = ', '.join(['%s'] * len(ids))
            print(f"[LOG] Atualizando status para 'processando' para os IDs: {ids}")
            cursor.execute(f"UPDATE fila_cnpj SET status = 'processando' WHERE id IN ({id_placeholders})", ids)
            conn.commit()
            print(f"[LOG] Tarefas marcadas como processando: {ids}")
        return ids
    except Exception as e:
        print(f"[ERRO] Erro ao verificar tarefas pendentes em lote: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def process_cnpj_on_website_sync(args, headless=True):
    cnpj_obj, fila_id = args
    try:
        # Criar um novo loop de eventos para cada thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Passar os tempos de espera para o web_service
        result = loop.run_until_complete(
            CNPJService.process_cnpj_on_website(
                cnpj_obj, 
                headless=headless, 
                fila_id=fila_id,
                wait_times=WAIT_TIMES  # Passar os tempos de espera configurados
            )
        )
        loop.close()
        return result
    except Exception as e:
        print(f"[ERRO] process_cnpj_on_website_sync falhou para CNPJ {cnpj_obj.cnpj}: {e}")
        print(traceback.format_exc())
        return {
            "status": "error",
            "message": f"Falha no processamento: {str(e)}",
            "resultado": f"[ERRO] {str(e)}"
        }

def processa_cnpj(fila_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verificar se a tarefa ainda precisa ser processada (poderia ter sido pega por outro worker)
        cursor.execute("SELECT * FROM fila_cnpj WHERE id = %s AND status = 'processando'", (fila_id,))
        row = cursor.fetchone()
        if not row:
            print(f"Tarefa {fila_id} não encontrada ou não está em processamento. Ignorando.")
            if cursor: cursor.close()
            if conn: conn.close()
            return

        # Criar objeto CNPJ com todos os campos disponíveis
        cnpj_obj = CNPJ(
            cnpj=row['cnpj'],
            razao_social=row.get('razao_social') or "",
            municipio=row.get('municipio') or ""
        )
        # Garantir que headless=True
        print(f"Processando CNPJ {row['cnpj']} com headless=True (fila_id={fila_id})")
        result = process_cnpj_on_website_sync((cnpj_obj, fila_id), headless=True)
        print(f"==== RESULTADO DO WEBSERVICE (fila_id={fila_id}) ====")
        print(result)
        print("===============================")
        
        if not result:
            status = "erro"
            resultado = "[ERRO] Nenhum resultado retornado do WebService"
            full_result = ""
            print(f"[ERRO] WebService retornou None para fila_id={fila_id}")
        elif result.get("status") == "error":
            status = "erro"
            resultado = f"[ERRO] Falha no site: {result.get('message', 'Sem detalhes')}"
            full_result = result.get("full_result", "")
        elif result.get("status") == "success":
            status = "concluido"
            if result.get("resultado"):
                resultado = result.get("resultado")
            elif result.get("status_divida"):
                resultado = result.get("status_divida")
            elif result.get("texto_completo"):
                resultado = result.get("texto_completo")[:1000]
            else:
                resultado = "Processado com sucesso, mas sem texto específico"
            full_result = result.get("full_result", "")
            print(f"Resultado final que será salvo no banco para fila_id={fila_id}: {resultado[:100]}...")
        else:
            status = "erro"
            erro_detalhes = ""
            if result.get("message"):
                erro_detalhes = f" - {result.get('message')}"
            if result.get("texto_completo"):
                erro_parcial = result.get("texto_completo", "")[:100]
                resultado = f"[ERRO] Texto capturado, mas não foi possível determinar o status (pendência/não pendência){erro_detalhes}. Texto parcial: {erro_parcial}..."
            else:
                resultado = f"[ERRO] Texto não encontrado ou não retornado pelo WebService{erro_detalhes}"
            full_result = result.get("full_result", "")
        if resultado is None:
            resultado = "[ERRO] Resultado vazio"
        if full_result is None:
            full_result = ""
        print(f"[LOG] Atualizando fila_cnpj id={fila_id} com status='{status}'")
        cursor.execute(
            "UPDATE fila_cnpj SET status = %s, resultado = %s, full_result = %s WHERE id = %s",
            (status, resultado, full_result, fila_id)
        )
        conn.commit()
        print(f"[LOG] UPDATE executado e commit realizado para id={fila_id}")
        
    except Exception as e:
        print(f"[ERRO] Exceção inesperada no worker para fila_id={fila_id}: {e}")
        print(traceback.format_exc())
        
        # Tentar atualizar o status para erro caso tenha ocorrido um problema
        try:
            if conn and cursor:
                cursor.execute(
                    "UPDATE fila_cnpj SET status = %s, resultado = %s WHERE id = %s", 
                    ("erro", f"[ERRO] Exceção no worker: {str(e)}", fila_id)
                )
                conn.commit()
        except Exception as update_err:
            print(f"[ERRO] Não foi possível atualizar status para erro: {update_err}")
    finally:
        # Garantir que conexões sejam fechadas
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass

def callback(ch, method, properties, body):
    fila_id = int(body.decode())
    def task():
        try:
            processa_cnpj(fila_id)
        except Exception as e:
            print(f"[ERRO CRÍTICO] Falha na execução da tarefa para fila_id={fila_id}: {e}")
            print(traceback.format_exc())
        finally:
            # Sempre confirmar a mensagem para evitar deadlocks na fila
            try:
                ch.connection.add_callback_threadsafe(lambda: ch.basic_ack(delivery_tag=method.delivery_tag))
            except Exception as ack_err:
                print(f"[ERRO] Não foi possível confirmar mensagem: {ack_err}")
    
    # Adicionar pequeno delay aleatório para evitar sobrecarga quando múltiplos workers recebem mensagens ao mesmo tempo
    time.sleep(random.uniform(0.1, 1.0))
    executor.submit(task)

# Conectar com retentativas e backoff exponencial
def connect_to_rabbitmq():
    max_retries = 5
    retry_count = 0
    connection = None
    
    while retry_count < max_retries and connection is None:
        try:
            print(f"Tentando conectar ao RabbitMQ em {RABBITMQ_HOST} (tentativa {retry_count+1}/{max_retries})...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                connection_attempts=3,
                retry_delay=5,
                heartbeat=600  # Heartbeat a cada 10 minutos para manter conexão viva
            ))
            print("Conexão com RabbitMQ estabelecida com sucesso!")
            return connection
        except Exception as e:
            retry_count += 1
            print(f"Erro ao conectar ao RabbitMQ: {str(e)}")
            if retry_count >= max_retries:
                raise Exception(f"Falha ao conectar ao RabbitMQ após {max_retries} tentativas")
            sleep_time = 5 * (2 ** (retry_count - 1))  # Backoff exponencial
            print(f"Tentando novamente em {sleep_time} segundos...")
            time.sleep(sleep_time)

def modo_batch(batchsize=50, workers=3):
    print("[LOG] Entrou no modo_batch")
    global executor, WAIT_TIMES
    executor = ThreadPoolExecutor(max_workers=workers)
    WAIT_TIMES = calculate_wait_time(batchsize)
    print(f"[LOG] Tempos de espera configurados para batch size {batchsize}: {WAIT_TIMES}")
    while True:
        print("[LOG] Loop principal do modo_batch rodando...")
        try:
            tarefas_ids = verificar_tarefas_pendentes_lote(batchsize)
            print(f"[LOG] IDs retornados para processamento: {tarefas_ids}")
            if not tarefas_ids:
                print("[LOG] Sem tarefas pendentes. Aguardando 10 segundos...")
                time.sleep(10)
                continue
            futures = []
            for fila_id in tarefas_ids:
                print(f"[LOG] Submetendo tarefa {fila_id} para processamento.")
                time.sleep(WAIT_TIMES["between_tasks"])
                futures.append(executor.submit(processa_cnpj, fila_id))
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"[ERRO] Erro em uma das tarefas do lote: {e}")
            print(f"[LOG] Lote de {len(tarefas_ids)} tarefas concluído.")
            if len(tarefas_ids) < batchsize:
                print(f"[LOG] Menos de {batchsize} tarefas pendentes. Aguardando {WAIT_TIMES['between_tasks']} segundos antes de verificar novamente...")
                time.sleep(WAIT_TIMES["between_tasks"])
            else:
                pausa_entre_lotes = WAIT_TIMES["between_tasks"] * 3
                print(f"[LOG] Pausa de {pausa_entre_lotes} segundos entre lotes grandes...")
                time.sleep(pausa_entre_lotes)
        except Exception as e:
            print(f"[ERRO] Erro no modo batch: {e}")
            print(traceback.format_exc())
            print(f"[LOG] Aguardando {WAIT_TIMES['page_load']} segundos antes de tentar novamente...")
            time.sleep(WAIT_TIMES["page_load"])

def modo_fila():
    """
    Executa o worker no modo tradicional, consumindo da fila do RabbitMQ
    """
    print("Iniciando modo fila com RabbitMQ")
    # Conectar ao RabbitMQ e iniciar consumo com prefetch reduzido
    try:
        connection = connect_to_rabbitmq()
        channel = connection.channel()
        channel.queue_declare(queue='fila_cnpj')
        
        # Reduzir prefetch_count de 10 para 3 para evitar sobrecarga quando múltiplos workers estão rodando
        channel.basic_qos(prefetch_count=3)
        
        channel.basic_consume(queue='fila_cnpj', on_message_callback=callback)
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Worker interrompido pelo usuário")
    except Exception as e:
        print(f"Erro no worker: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Worker para processamento de CNPJs')
    parser.add_argument('--modo', type=str, choices=['fila', 'batch'], default='fila',
                        help='Modo de operação: fila (RabbitMQ) ou batch (verificação em lote)')
    parser.add_argument('--batchsize', type=int, default=50,
                        help='Número de tarefas a serem processadas por lote (apenas para modo batch)')
    parser.add_argument('--workers', type=int, default=3,
                        help='Número de workers paralelos (apenas para modo batch)')
    
    args = parser.parse_args()
    
    if args.modo == 'batch':
        modo_batch(batchsize=args.batchsize, workers=args.workers)
    else:
        modo_fila() 
        