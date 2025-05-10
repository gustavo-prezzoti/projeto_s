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
    # Valores base aumentados para lidar com conexões lentas
    if batchsize <= 5:
        base_wait = 45  # Aumentado de 20 para 45
    elif batchsize <= 20:
        base_wait = 60  # Aumentado de 35 para 60
    elif batchsize <= 50:
        base_wait = 75  # Aumentado de 40 para 75
    else:
        base_wait = 120  # Aumentado de 90 para 120
    
    # Calcula diferentes tempos baseados no tempo base
    return {
        "page_load": base_wait,                      # Tempo para carregar página
        "after_click": max(20, base_wait * 0.5),     # Tempo após cliques (mínimo 20s)
        "form_fill": max(10, base_wait * 0.3),       # Tempo para preenchimento de formulário (mínimo 10s)
        "element_wait": max(30, base_wait * 0.7),    # Timeout para esperar elementos (mínimo 30s)
        "between_tasks": max(5, base_wait * 0.2)     # Tempo entre tarefas do batch (mínimo 5s)
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
    """Callback para processar mensagens da fila"""
    fila_id = body.decode('utf-8').strip()
    print(f"Recebido ID {fila_id} da fila")
    
    # Verificar se este ID está na lista de ignorados
    connection = None
    channel = None
    try:
        # Conectar ao RabbitMQ para verificar a fila de ignorados
        connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
        channel = connection.channel()
        # Declarar a fila de ignorados se não existir
        channel.queue_declare(queue='fila_cnpj_ignorados', durable=True)
        
        # Tentar obter uma mensagem da fila de ignorados sem consumir
        method_frame, header_frame, body_ignorado = channel.basic_get(
            queue='fila_cnpj_ignorados',
            auto_ack=False
        )
        
        # Se existe alguma mensagem e é o ID atual
        if method_frame and body_ignorado and body_ignorado.decode('utf-8').strip() == fila_id:
            print(f"ID {fila_id} está na lista de ignorados. Pulando processamento.")
            # Confirmar consumo desta mensagem da fila de ignorados
            channel.basic_ack(delivery_tag=method_frame.delivery_tag)
            # Confirmar consumo da mensagem original
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
    except Exception as e:
        print(f"Erro ao verificar fila de ignorados: {str(e)}")
    finally:
        if connection and connection.is_open:
            connection.close()

    def task():
        """Tarefa para processar o ID"""
        try:
            processa_cnpj(fila_id)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"Processamento de {fila_id} concluído e confirmado!")
        except Exception as e:
            print(f"Erro no processamento de {fila_id}: {str(e)}")
            print(traceback.format_exc())
            # Se ocorrer erro, tentar confirmar recebimento mesmo assim para evitar loop
            try:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                print(f"Mensagem {fila_id} confirmada após erro!")
            except:
                print(f"Não foi possível confirmar a mensagem {fila_id} após erro.")

    # Submeter à thread pool para processamento paralelo
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

def modo_batch(batchsize=30, workers=2):
    """
    Processa CNPJs em lotes (modo batch) sem usar RabbitMQ
    
    Args:
        batchsize: Tamanho máximo de cada lote (padrão: 30)
        workers: Número de workers paralelos (padrão: 2)
    """
    print("[LOG] Entrou no modo_batch")
    global executor, WAIT_TIMES
    
    # Limitar workers para 2 para evitar sobrecarga
    workers = min(workers, 2)
    
    # Ajustar batchsize se excessivamente grande
    batchsize = min(batchsize, 50)
    
    executor = ThreadPoolExecutor(max_workers=workers)
    WAIT_TIMES = calculate_wait_time(batchsize)
    print(f"[LOG] Tempos de espera configurados para batch size {batchsize}: {WAIT_TIMES}")
    print(f"[LOG] Usando {workers} workers paralelos")
    
    # Controle da carga de trabalho
    ciclos_sem_tarefas = 0
    max_ciclos_sem_tarefas = 6  # Após 6 ciclos sem tarefas, aumenta a pausa
    
    while True:
        print("[LOG] Loop principal do modo_batch rodando...")
        try:
            tarefas_ids = verificar_tarefas_pendentes_lote(batchsize)
            print(f"[LOG] IDs retornados para processamento: {tarefas_ids}")
            
            if not tarefas_ids:
                ciclos_sem_tarefas += 1
                pausa = WAIT_TIMES["page_load"] if ciclos_sem_tarefas <= max_ciclos_sem_tarefas else 60
                print(f"[LOG] Sem tarefas pendentes. Aguardando {pausa} segundos... (ciclo {ciclos_sem_tarefas})")
                time.sleep(pausa)
                continue
            
            # Resetar contador quando encontrar tarefas
            ciclos_sem_tarefas = 0
            
            # Iniciar com uma pausa para garantir que processos antigos do Chrome estejam encerrados
            pausa_inicial = 15
            print(f"[LOG] Pausa inicial de {pausa_inicial} segundos antes de iniciar novo lote...")
            time.sleep(pausa_inicial)
            
            futures = []
            for i, fila_id in enumerate(tarefas_ids):
                print(f"[LOG] Submetendo tarefa {fila_id} para processamento ({i+1}/{len(tarefas_ids)}).")
                # Pausa maior entre submissões
                pausa_entre_submissoes = WAIT_TIMES["between_tasks"] * 3
                print(f"[LOG] Aguardando {pausa_entre_submissoes} segundos antes de submeter próxima tarefa...")
                time.sleep(pausa_entre_submissoes)
                futures.append(executor.submit(processa_cnpj, fila_id))
            
            # Aguardar todas as tarefas concluírem
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"[ERRO] Erro em uma das tarefas do lote: {e}")
                    print(traceback.format_exc())
            
            print(f"[LOG] Lote de {len(tarefas_ids)} tarefas concluído.")
            
            if len(tarefas_ids) < batchsize:
                pausa_lote_pequeno = WAIT_TIMES["between_tasks"] * 2
                print(f"[LOG] Menos de {batchsize} tarefas pendentes. Aguardando {pausa_lote_pequeno} segundos antes de verificar novamente...")
                time.sleep(pausa_lote_pequeno)
            else:
                pausa_entre_lotes = WAIT_TIMES["page_load"]
                print(f"[LOG] Pausa de {pausa_entre_lotes} segundos entre lotes grandes...")
                time.sleep(pausa_entre_lotes)
        except Exception as e:
            print(f"[ERRO] Erro no modo batch: {e}")
            print(traceback.format_exc())
            print(f"[LOG] Aguardando {WAIT_TIMES['page_load']} segundos antes de tentar novamente...")
            time.sleep(WAIT_TIMES['page_load'])

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
    parser.add_argument('--batchsize', type=int, default=30,
                        help='Número de tarefas a serem processadas por lote (apenas para modo batch)')
    parser.add_argument('--workers', type=int, default=2,
                        help='Número de workers paralelos (apenas para modo batch)')
    
    args = parser.parse_args()
    
    if args.modo == 'batch':
        modo_batch(batchsize=args.batchsize, workers=args.workers)
    else:
        modo_fila() 
        