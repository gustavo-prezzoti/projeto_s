import pika
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.models.cnpj import CNPJ
from app.services.cnpj_service import CNPJService
from app.database.config import (
    get_supabase_client,
    update_queue_item
)
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
RABBITMQ_HOST = "rabbitmq-cnpj" if is_docker_container_name_resolvable("rabbitmq-cnpj") else "localhost"

# Variável global para armazenar tempos de espera
WAIT_TIMES = calculate_wait_time(20)  # Valor padrão inicial

print(f"Usando RabbitMQ em: {RABBITMQ_HOST}")
print(f"Tempos de espera iniciais: {WAIT_TIMES}")

# Lista de tarefas ignoradas (local)
ignored_tasks = set()

def should_ignore_task(fila_id):
    """
    Verifica se uma tarefa deve ser ignorada
    
    Args:
        fila_id: ID da tarefa na fila
        
    Returns:
        True se a tarefa deve ser ignorada, False caso contrário
    """
    return fila_id in ignored_tasks

def add_to_ignore_list(fila_id):
    """
    Adiciona uma tarefa à lista de ignorados
    
    Args:
        fila_id: ID da tarefa na fila
    """
    ignored_tasks.add(fila_id)

def get_pending_tasks(limit=50):
    """
    Obtém tarefas pendentes do banco de dados
    
    Args:
        limit: Limite de tarefas a retornar
        
    Returns:
        Lista de tarefas pendentes
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fila_cnpj").select("*").eq("status", "pendente").limit(limit).execute()
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        print(f"[ERRO] Erro ao obter tarefas pendentes: {e}")
        return []

def update_task_status(fila_id, status, resultado=None, status_divida=None, pdf_path=None, full_result=None):
    """
    Atualiza o status de uma tarefa no banco de dados
    
    Args:
        fila_id: ID da tarefa na fila
        status: Novo status (pendente, processando, concluido, erro, ignorado)
        resultado: Resultado do processamento (opcional)
        status_divida: Status da dívida (opcional)
        pdf_path: Caminho para o PDF (opcional)
        full_result: Resultado completo (opcional)
        
    Returns:
        True se a atualização foi bem-sucedida, False caso contrário
    """
    try:
        update_data = {"status": status}
        
        if resultado is not None:
            update_data["resultado"] = resultado
            
        if status_divida is not None:
            update_data["status_divida"] = status_divida
            
        if pdf_path is not None:
            update_data["pdf_path"] = pdf_path
            
        if full_result is not None:
            update_data["full_result"] = full_result
            
        # Atualizar no banco
        return update_queue_item(fila_id, update_data)
    except Exception as e:
        print(f"[ERRO] Erro ao atualizar status da tarefa {fila_id}: {e}")
        return False

def verificar_tarefas_pendentes_lote(limit=50):
    print(f"[LOG] Chamando verificar_tarefas_pendentes_lote com limit={limit}")
    try:
        print("[LOG] Buscando tarefas pendentes no Supabase")
        tasks = get_pending_tasks(limit)
        print(f"[LOG] Encontradas {len(tasks)} tarefas pendentes")
        
        if not tasks:
            print("[LOG] Nenhuma tarefa pendente encontrada.")
            return []
            
        return [task["id"] for task in tasks]
    except Exception as e:
        print(f"[ERRO] Erro ao verificar tarefas pendentes em lote: {e}")
        return []

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
    try:
        # Verificar se a tarefa ainda precisa ser processada (poderia ter sido pega por outro worker)
        task = get_task_by_id(fila_id)
        if not task or task.get("status") != "processando":
            print(f"Tarefa {fila_id} não encontrada ou não está em processamento. Ignorando.")
            return

        # Verificar se a tarefa está na lista de ignorados
        if should_ignore_task(fila_id):
            print(f"Tarefa {fila_id} na lista de ignorados. Ignorando processamento.")
            update_task_status(fila_id, "ignorado", "Tarefa ignorada pelo worker")
            return

        # Criar objeto CNPJ com todos os campos disponíveis
        cnpj_obj = CNPJ(
            cnpj=task['cnpj'],
            razao_social=task.get('razao_social') or "",
            municipio=task.get('municipio') or ""
        )
        # Garantir que headless=True
        print(f"Processando CNPJ {task['cnpj']} com headless=True (fila_id={fila_id})")
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
            else:
                resultado = "Processado com sucesso, sem retorno específico"
            
            if not resultado:
                resultado = "Resultado vazio"
            
            if len(resultado) > 2000:
                resultado = resultado[:1997] + "..."
                
            full_result = result.get("full_result", "")
        else:
            status = "erro"
            resultado = "[ERRO] Status desconhecido retornado pelo WebService"
            full_result = str(result)
            
        # Atualizar status da tarefa no banco
        status_divida = result.get("status_divida") if result else None
        pdf_path = next(iter(result.get("screenshots", [])), None) if result else None
            
        update_task_status(
            fila_id, 
            status, 
            resultado, 
            status_divida, 
            pdf_path, 
            full_result
        )
            
        print(f"CNPJ {task['cnpj']} processado com status: {status}")
    except Exception as e:
        print(f"[ERRO] Erro ao processar CNPJ de fila_id={fila_id}: {e}")
        print(traceback.format_exc())
        try:
            # Tentativa final de marcar como erro no banco
            update_task_status(
                fila_id, 
                "erro", 
                f"[ERRO] Exceção no processamento: {str(e)}", 
                None, 
                None, 
                traceback.format_exc()
            )
        except Exception as update_error:
            print(f"[ERRO FATAL] Não foi possível atualizar status da tarefa no banco: {update_error}")

def callback(ch, method, properties, body):
    try:
        fila_id = int(body.decode())
        print(f" [x] Recebido {fila_id}")
        
        # Verificar se a tarefa está na lista de ignorados
        if should_ignore_task(fila_id):
            print(f"Tarefa {fila_id} na lista de ignorados. Ignorando processamento e confirmando recebimento.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        # Verifica se o fila_id existe e está com status 'pendente' ou 'processando'
        task = get_task_by_id(fila_id)
        if not task or (task.get("status") != "pendente" and task.get("status") != "processando"):
            print(f"Tarefa {fila_id} não encontrada, não está pendente ou não está em processamento. Confirmando recebimento.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        # Atualizar status para 'processando' se estiver 'pendente'
        if task.get("status") == "pendente":
            update_task_status(fila_id, "processando")
            
        def task():
            try:
                processa_cnpj(fila_id)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                print(f"[ERRO] Thread de processamento falhou para fila_id={fila_id}: {str(e)}")
                # Mesmo com falha, confirma o recebimento para não reprocessar
                try:
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as ack_error:
                    print(f"[ERRO] Falha ao confirmar recebimento para fila_id={fila_id}: {str(ack_error)}")
                # Tentar marcar como erro no banco
                try:
                    update_task_status(
                        fila_id, 
                        "erro", 
                        f"[ERRO CRÍTICO] Falha na thread de processamento: {str(e)}"
                    )
                except Exception as db_error:
                    print(f"[ERRO FATAL] Falha ao atualizar status para erro no banco para fila_id={fila_id}: {str(db_error)}")
        
        # Executa o processamento em uma thread separada
        executor.submit(task)
        
    except Exception as e:
        print(f"[ERRO] Callback falhou: {str(e)}")
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as ack_error:
            print(f"[ERRO] Falha ao confirmar recebimento após erro: {str(ack_error)}")

def connect_to_rabbitmq():
    retry_count = 0
    max_retries = 10
    retry_delay = 5
    
    while retry_count < max_retries:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()
            channel.queue_declare(queue='fila_cnpj')
            channel.queue_declare(queue='fila_cnpj_ignorados', durable=True)
            channel.basic_qos(prefetch_count=10)  # Aumentar o prefetch para melhor throughput
            
            # Consumir mensagens da fila
            channel.basic_consume(queue='fila_cnpj', on_message_callback=callback)
            
            print(' [*] Aguardando mensagens. Para sair pressione CTRL+C')
            
            # Retornar os objetos de conexão
            return connection, channel
        except pika.exceptions.AMQPConnectionError as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"Erro ao conectar ao RabbitMQ: {e}. Tentando novamente em {retry_delay} segundos...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 60)  # Exponential backoff com limite
            else:
                print(f"Falha ao conectar ao RabbitMQ após {max_retries} tentativas: {e}")
                return None, None
        except Exception as e:
            print(f"Erro inesperado ao conectar ao RabbitMQ: {e}")
            return None, None

def modo_batch(batchsize=30, workers=2):
    global WAIT_TIMES
    
    # Ajustar os tempos de espera com base no tamanho do batch
    WAIT_TIMES = calculate_wait_time(batchsize)
    print(f"Modo batch configurado com batchsize={batchsize}, workers={workers}")
    print(f"Tempos de espera ajustados: {WAIT_TIMES}")
    
    # Limitar o número de workers para evitar sobrecarga
    max_safe_workers = min(workers, 5)
    if max_safe_workers < workers:
        print(f"⚠️ Número de workers limitado a {max_safe_workers} para evitar sobrecarga (solicitado: {workers})")
    
    print(f"Verificando até {batchsize} tarefas pendentes...")
    ids_pendentes = verificar_tarefas_pendentes_lote(batchsize)
    
    if not ids_pendentes:
        print("Nenhuma tarefa pendente encontrada.")
        return
        
    print(f"Encontradas {len(ids_pendentes)} tarefas pendentes.")
    
    # Preparar lista de objetos CNPJ e IDs para processamento
    tasks = []
    for fila_id in ids_pendentes:
        try:
            task = get_task_by_id(fila_id)
            if not task:
                print(f"Tarefa com ID {fila_id} não encontrada no banco. Ignorando.")
                continue
                
            cnpj_obj = CNPJ(
                cnpj=task['cnpj'],
                razao_social=task.get('razao_social') or "",
                municipio=task.get('municipio') or ""
            )
            
            tasks.append((cnpj_obj, fila_id))
        except Exception as e:
            print(f"Erro ao preparar tarefa {fila_id} para processamento: {e}")
            
    if not tasks:
        print("Nenhuma tarefa válida para processar.")
        return
        
    print(f"Processando {len(tasks)} tarefas em modo batch com {max_safe_workers} workers...")
    
    # Processar as tarefas com limite de workers
    with ThreadPoolExecutor(max_workers=max_safe_workers) as ex:
        batch_results = []
        for result in ex.map(lambda args: process_cnpj_on_website_sync(args, headless=True), tasks):
            batch_results.append(result)
    
    print(f"Processamento em batch concluído. Resultados: {len(batch_results)} tarefas processadas.")
    
    # Atualizar o status das tarefas no banco
    for i, (cnpj_obj, fila_id) in enumerate(tasks):
        try:
            result = batch_results[i] if i < len(batch_results) else None
            
            if not result:
                status = "erro"
                resultado = "[ERRO] Nenhum resultado retornado do processamento em batch"
                full_result = ""
            elif result.get("status") == "error":
                status = "erro"
                resultado = f"[ERRO] Falha no site: {result.get('message', 'Sem detalhes')}"
                full_result = result.get("full_result", "")
            elif result.get("status") == "success":
                status = "concluido"
                resultado = result.get("resultado") or result.get("status_divida") or "Processado com sucesso, sem retorno específico"
                if len(resultado) > 2000:
                    resultado = resultado[:1997] + "..."
                full_result = result.get("full_result", "")
            else:
                status = "erro"
                resultado = "[ERRO] Status desconhecido retornado pelo processamento em batch"
                full_result = str(result)
                
            # Atualizar status da tarefa no banco
            status_divida = result.get("status_divida") if result else None
            pdf_path = next(iter(result.get("screenshots", [])), None) if result else None
                
            update_task_status(
                fila_id, 
                status, 
                resultado, 
                status_divida, 
                pdf_path, 
                full_result
            )
                
            print(f"CNPJ {cnpj_obj.cnpj} (fila_id={fila_id}) processado em batch com status: {status}")
        except Exception as e:
            print(f"[ERRO] Falha ao atualizar status da tarefa {fila_id} após processamento em batch: {e}")
    
    print("Processamento em batch completo!")

def modo_fila():
    print("Iniciando worker no modo fila...")
    
    # Conectar ao RabbitMQ
    connection, channel = connect_to_rabbitmq()
    
    if not connection or not channel:
        print("Falha ao conectar ao RabbitMQ. Encerrando worker.")
        return
    
    try:
        # Bloquear e consumir mensagens da fila
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Worker interrompido pelo usuário.")
    except Exception as e:
        print(f"Erro no modo fila: {e}")
    finally:
        try:
            if connection and connection.is_open:
                connection.close()
                print("Conexão com RabbitMQ fechada.")
        except Exception as close_error:
            print(f"Erro ao fechar conexão com RabbitMQ: {close_error}")

def get_task_by_id(fila_id):
    """
    Obtém uma tarefa específica pelo ID
    
    Args:
        fila_id: ID da tarefa na fila
        
    Returns:
        Dados da tarefa ou None se não encontrada
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fila_cnpj").select("*").eq("id", fila_id).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"[ERRO] Erro ao obter tarefa {fila_id}: {e}")
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Worker para processamento de CNPJs')
    parser.add_argument('--modo', choices=['fila', 'batch'], default='fila', help='Modo de execução: fila (contínuo) ou batch (único)')
    parser.add_argument('--batchsize', type=int, default=30, help='Quantidade de CNPJs a processar em modo batch')
    parser.add_argument('--workers', type=int, default=2, help='Número de workers paralelos em modo batch')
    
    args = parser.parse_args()
    
    print(f"Worker iniciando em modo: {args.modo}")
    
    if args.modo == 'batch':
        modo_batch(args.batchsize, args.workers)
    else:
        modo_fila() 
        