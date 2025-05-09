from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
import os
import shutil
from uuid import uuid4
import asyncio
from concurrent.futures import ThreadPoolExecutor
import tempfile
import mysql.connector
from datetime import datetime, timedelta
import re

from app.services.excel_service import ExcelService
from app.services.cnpj_service import CNPJService
from app.schemas.responses import CNPJProcessingResponse, CNPJResponse, ExcelValidationResponse, CNPJValidationItem
from app.services.queue_service import send_to_queue_and_db, MYSQL_HOST, check_cnpj_exists
from app.models.cnpj import CNPJ

router = APIRouter(prefix="/cnpj", tags=["CNPJ Processing"])

executor = ThreadPoolExecutor()

@router.post("/validate-excel", response_model=ExcelValidationResponse)
async def validate_cnpj_from_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None)
):
    """
    Upload an Excel file with CNPJ data and validate it against the database
    without processing or saving the data. Returns a list of new and existing CNPJs.
    
    Args:
        file: The Excel file containing CNPJ data
        sheet_name: Name of the sheet to process (optional)
        
    Returns:
        Validation results, distinguishing between new and existing CNPJs
    """
    temp_file_path = None
    try:
        # Validate file type
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400, 
                detail="Only Excel files (.xlsx or .xls) are supported"
            )
        
        # Create temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)
        
        # Save uploaded file
        temp_file_path = f"temp/{uuid4()}_{file.filename}"
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process the Excel file
        print(f"Processing Excel file for validation: {temp_file_path}")
        excel_data = await ExcelService.process_excel_file(temp_file_path, sheet_name)
        
        # Extract CNPJ information
        print("Extracting CNPJ information for validation")
        cnpjs = CNPJService.extract_cnpjs_from_excel_data(excel_data)
        
        if not cnpjs:
            print("No valid CNPJ data found in the Excel file for validation")
            raise HTTPException(
                status_code=400,
                detail="No valid CNPJ data found in the Excel file"
            )
            
        print(f"Found {len(cnpjs)} CNPJs for validation")
            
        # Find duplicates in the file
        print("Finding duplicates in Excel file")
        duplicates = CNPJService.find_duplicates_in_excel(cnpjs)
        duplicate_cnpjs = set()
        for cnpj_str, occurrences in duplicates.items():
            duplicate_cnpjs.add(cnpj_str)
        print(f"Found {len(duplicate_cnpjs)} duplicate CNPJs in file")
        
        # Get unique CNPJs to avoid duplicates in the file
        print("Getting unique CNPJs for validation")
        unique_cnpjs = CNPJService.get_unique_cnpjs(cnpjs)
        print(f"Found {len(unique_cnpjs)} unique CNPJs for validation")
        
        # Validate against database
        print("Validating against database")
        new_cnpjs, existing_cnpjs = CNPJService.validate_cnpjs_against_db(unique_cnpjs)
        print(f"Validation result - New CNPJs: {len(new_cnpjs)}, Existing CNPJs: {len(existing_cnpjs)}")
        
        # Prepare validation items for response
        validation_items = []
        
        # Add new CNPJs to response
        print("Preparing validation items for new CNPJs")
        for cnpj in new_cnpjs:
            validation_items.append(CNPJValidationItem(
                nome=cnpj.razao_social,
                cnpj=cnpj.cnpj,
                cnpj_formatado=CNPJService.format_cnpj(cnpj.cnpj),
                razao_social=cnpj.razao_social,
                municipio=cnpj.municipio,
                status="new",
                existing=False,
                duplicate_in_file=cnpj.cnpj in duplicate_cnpjs,
                duplicate_count=len(duplicates.get(cnpj.cnpj, [])) if cnpj.cnpj in duplicate_cnpjs else 0
            ))
        
        # Add existing CNPJs to response
        print("Preparing validation items for existing CNPJs")
        for item in existing_cnpjs:
            cnpj = item["cnpj_obj"]
            db_record = item["db_record"]
            validation_items.append(CNPJValidationItem(
                nome=cnpj.razao_social,
                cnpj=cnpj.cnpj,
                cnpj_formatado=CNPJService.format_cnpj(cnpj.cnpj),
                razao_social=cnpj.razao_social,
                municipio=cnpj.municipio,
                status=db_record.get("status", "unknown"),
                existing=True,
                duplicate_in_file=cnpj.cnpj in duplicate_cnpjs,
                duplicate_count=len(duplicates.get(cnpj.cnpj, [])) if cnpj.cnpj in duplicate_cnpjs else 0,
                db_record=db_record
            ))
        
        print(f"Total validation items: {len(validation_items)}")
        
        return ExcelValidationResponse(
            total=len(validation_items),
            new_items=len(new_cnpjs),
            existing_items=len(existing_cnpjs),
            duplicate_items=len(duplicate_cnpjs),
            cnpjs=validation_items
        )
        
    except HTTPException as he:
        # Re-raise HTTP exceptions without wrapping
        print(f"HTTP Exception in validation: {he.detail}")
        raise
    except Exception as e:
        # Handle other exceptions
        import traceback
        error_msg = f"Error validating file: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        # Clean up the temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except PermissionError:
                # Se não puder remover o arquivo agora, tente fechar qualquer handle aberto primeiro
                # e agendar a remoção para depois
                print(f"Não foi possível remover o arquivo temporário: {temp_file_path}. Será removido depois.")
                import gc
                gc.collect()  # Força o coletor de lixo
                
                # Agendar remoção para um momento posterior
                def remove_later(file_path, retries=3):
                    import time
                    for i in range(retries):
                        time.sleep(2)  # Espera 2 segundos
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                print(f"Arquivo removido com sucesso após {i+1} tentativas: {file_path}")
                                break
                        except:
                            pass
                
                # Inicia um thread para remover o arquivo mais tarde
                import threading
                t = threading.Thread(target=remove_later, args=(temp_file_path,))
                t.daemon = True
                t.start()

@router.post("/process-selected", response_model=CNPJProcessingResponse)
async def process_selected_cnpjs(
    cnpjs: List[str]
):
    """
    Process a list of selected CNPJs from the validation result
    
    Args:
        cnpjs: List of CNPJ strings to process
        
    Returns:
        Result of processing the selected CNPJs
    """
    try:
        if not cnpjs:
            raise HTTPException(
                status_code=400,
                detail="No CNPJs provided for processing"
            )
        
        print(f"Received {len(cnpjs)} CNPJs for processing: {cnpjs}")
        
        # Fetch company names from database if available, otherwise use a placeholder
        processed_cnpjs = []
        for cnpj_str in cnpjs:
            # Clean the CNPJ
            cleaned_cnpj = re.sub(r'[^\d]', '', cnpj_str)
            print(f"Processing CNPJ: {cnpj_str} -> Cleaned: {cleaned_cnpj}")
            
            # Skip invalid CNPJs (too short or too long)
            if len(cleaned_cnpj) < 8 or len(cleaned_cnpj) > 14:
                print(f"Skipping invalid CNPJ: {cleaned_cnpj} (length={len(cleaned_cnpj)})")
                continue
            
            # Pad with zeros if needed to get to 14 digits
            if len(cleaned_cnpj) < 14:
                cleaned_cnpj = cleaned_cnpj.zfill(14)
                print(f"Padded CNPJ: {cleaned_cnpj}")
            
            # Check if this CNPJ exists in the database
            print(f"Checking if CNPJ exists in database: {cleaned_cnpj}")
            exists, record = check_cnpj_exists(cleaned_cnpj)
            if exists and record:
                nome = record.get("nome", "Empresa")
                print(f"CNPJ exists in database: {cleaned_cnpj}, name: {nome}")
            else:
                nome = "Empresa"  # Default placeholder
                print(f"CNPJ not found in database: {cleaned_cnpj}, using default name")
            
            # Create CNPJ object
            cnpj_obj = CNPJ(
                cnpj=cleaned_cnpj,
                razao_social=nome,
                municipio=record.get("municipio", "")
            )
            
            # Send to queue and DB
            print(f"Sending CNPJ to queue and DB: {cleaned_cnpj}")
            send_to_queue_and_db(cnpj_obj)
            processed_cnpjs.append(cnpj_obj)
        
        print(f"Processed {len(processed_cnpjs)} CNPJs")
        return CNPJProcessingResponse(
            total_processed=len(processed_cnpjs),
            cnpjs=[]
        )
        
    except HTTPException as he:
        # Re-raise HTTP exceptions without wrapping
        print(f"HTTP Exception in process-selected: {he.detail}")
        raise
    except Exception as e:
        # Handle other exceptions
        import traceback
        error_msg = f"Error processing selected CNPJs: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/process", response_model=CNPJProcessingResponse)
async def process_cnpj_from_excel(
    file: UploadFile = File(...)
):
    """
    Upload an Excel file with CNPJ data, process it, and interact with the website.
    Will always delete existing records and create new ones.
    
    Args:
        file: The Excel file containing CNPJ data
        
    Returns:
        Result of CNPJ processing and web interaction
    """
    temp_file_path = None
    try:
        headless = False
        # Validate file type
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=400, 
                detail="Only Excel files (.xlsx or .xls) are supported"
            )
        # Create temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)
        # Save uploaded file
        temp_file_path = f"temp/{uuid4()}_{file.filename}"
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # Process the Excel file
        print(f"Processing Excel file: {temp_file_path}")
        excel_data = await ExcelService.process_excel_file(temp_file_path, None)  # Sempre usa a primeira planilha
        # Extract CNPJ information
        print("Extracting CNPJ information")
        cnpjs = CNPJService.extract_cnpjs_from_excel_data(excel_data)
        if not cnpjs:
            print("No valid CNPJ data found in the Excel file")
            raise HTTPException(
                status_code=400,
                detail="No valid CNPJ data found in the Excel file"
            )
        print(f"Found {len(cnpjs)} CNPJs")
        # Get unique CNPJs to avoid duplicates
        print("Getting unique CNPJs")
        unique_cnpjs = CNPJService.get_unique_cnpjs(cnpjs)
        print(f"Found {len(unique_cnpjs)} unique CNPJs")
        
        cnpjs_to_process = unique_cnpjs
            
        # Conectar ao banco de dados para excluir registros
        deleted_records = 0
        print("Will delete existing records before processing")
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)
        
        # Excluir registros existentes para cada CNPJ
        for cnpj in cnpjs_to_process:
            cursor.execute(
                "SELECT id FROM fila_cnpj WHERE cnpj = %s",
                (cnpj.cnpj,)
            )
            existing_records = cursor.fetchall()
            
            if existing_records:
                ids_to_delete = [record['id'] for record in existing_records]
                placeholders = ", ".join(["%s"] * len(ids_to_delete))
                cursor.execute(
                    f"DELETE FROM fila_cnpj WHERE id IN ({placeholders})",
                    ids_to_delete
                )
                deleted_records += len(ids_to_delete)
                print(f"Deleted {len(ids_to_delete)} existing records for CNPJ {cnpj.cnpj}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Total records deleted: {deleted_records}")
                
        # Enfileira cada CNPJ e registra no banco
        for cnpj in cnpjs_to_process:
            print(f"Sending CNPJ to queue: {cnpj.cnpj}")
            send_to_queue_and_db(cnpj)
            
        print(f"Total CNPJs processed: {len(cnpjs_to_process)}, Records deleted: {deleted_records}")
        return CNPJProcessingResponse(
            total_processed=len(cnpjs_to_process),
            cnpjs=[],
            deleted_records=deleted_records
        )
    except HTTPException as he:
        # Re-raise HTTP exceptions without wrapping
        print(f"HTTP Exception: {he.detail}")
        raise
    except Exception as e:
        # Handle other exceptions
        import traceback
        error_msg = f"Error processing file: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        # Clean up the temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except PermissionError:
                # Se não puder remover o arquivo agora, tente fechar qualquer handle aberto primeiro
                # e agendar a remoção para depois
                print(f"Não foi possível remover o arquivo temporário: {temp_file_path}. Será removido depois.")
                import gc
                gc.collect()  # Força o coletor de lixo
                # Agendar remoção para um momento posterior
                def remove_later(file_path, retries=3):
                    import time
                    for i in range(retries):
                        time.sleep(2)  # Espera 2 segundos
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                print(f"Arquivo removido com sucesso após {i+1} tentativas: {file_path}")
                                break
                        except:
                            pass
                # Inicia um thread para remover o arquivo mais tarde
                import threading
                t = threading.Thread(target=remove_later, args=(temp_file_path,))
                t.daemon = True
                t.start()

@router.post("/reprocess-pending", response_model=CNPJProcessingResponse)
async def reprocess_pending_cnpjs():
    """
    Reprocessar todos os CNPJs com status 'pendente' ou 'erro' no banco de dados
    
    Returns:
        Resultado da operação com o número total de CNPJs reenfileirados
    """
    try:
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Buscar todos os CNPJs pendentes ou com erro
        cursor.execute(
            "SELECT * FROM fila_cnpj WHERE status IN ('pendente', 'erro')"
        )
        pending_rows = cursor.fetchall()
        
        if not pending_rows:
            return CNPJProcessingResponse(
                total_processed=0,
                cnpjs=[]
            )
        
        # Reprocessar cada CNPJ pendente
        reprocessed_count = 0
        for row in pending_rows:
            cnpj_obj = CNPJ(
                cnpj=row['cnpj'],
                razao_social=row['nome'],
                municipio=row['municipio']
            )
            
            # Atualizar o status para pendente (caso estivesse com erro)
            cursor.execute(
                "UPDATE fila_cnpj SET status = %s WHERE id = %s",
                ("pendente", row['id'])
            )
            
            # Reenviar para a fila
            send_to_queue_and_db(cnpj_obj)
            reprocessed_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return CNPJProcessingResponse(
            total_processed=reprocessed_count,
            cnpjs=[]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs pendentes: {str(e)}")

@router.get("/consultar", response_model=Dict[str, Any])
async def consultar_cnpjs(
    status: Optional[str] = Query(None, description="Filtrar por status (pendente, processando, concluido, erro)"),
    data_inicio: Optional[str] = Query(None, description="Data inicial (formato YYYY-MM-DD)"),
    data_fim: Optional[str] = Query(None, description="Data final (formato YYYY-MM-DD)"),
    texto_erro: Optional[str] = Query(None, description="Filtrar por texto contido no resultado de erro")
):
    """
    Consultar CNPJs no banco de dados com filtros por status e data
    
    Args:
        status: Filtrar por status (pendente, processando, concluido, erro)
        data_inicio: Data inicial formato YYYY-MM-DD
        data_fim: Data final formato YYYY-MM-DD
        texto_erro: Filtrar por texto contido no resultado de erro
        
    Returns:
        Lista de CNPJs que correspondem aos filtros
    """
    try:
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)
        
        # Construir consulta SQL com filtros
        query = "SELECT * FROM fila_cnpj WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        if data_inicio:
            try:
                # Validar formato da data
                datetime.strptime(data_inicio, "%Y-%m-%d")
                query += " AND DATE(data_criacao) >= %s"
                params.append(data_inicio)
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Formato de data_inicio inválido. Use YYYY-MM-DD"
                )
        
        if data_fim:
            try:
                # Validar formato da data
                datetime.strptime(data_fim, "%Y-%m-%d")
                query += " AND DATE(data_criacao) <= %s"
                params.append(data_fim)
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Formato de data_fim inválido. Use YYYY-MM-DD"
                )
        
        if texto_erro:
            query += " AND resultado LIKE %s"
            params.append(f"%{texto_erro}%")
        
        # Adicionar ordenação por data de criação (mais recentes primeiro)
        query += " ORDER BY data_criacao DESC"
        
        # Executar consulta
        cursor.execute(query, params)
        cnpjs = cursor.fetchall()
        
        # Transformar as datas para string para serialização JSON
        for cnpj in cnpjs:
            if 'data_criacao' in cnpj and cnpj['data_criacao']:
                cnpj['data_criacao'] = cnpj['data_criacao'].isoformat()
            if 'data_atualizacao' in cnpj and cnpj['data_atualizacao']:
                cnpj['data_atualizacao'] = cnpj['data_atualizacao'].isoformat()
        
        # Calcular estatísticas
        total = len(cnpjs)
        pendentes = sum(1 for cnpj in cnpjs if cnpj['status'] == 'pendente')
        processando = sum(1 for cnpj in cnpjs if cnpj['status'] == 'processando')
        concluidos = sum(1 for cnpj in cnpjs if cnpj['status'] == 'concluido')
        erros = sum(1 for cnpj in cnpjs if cnpj['status'] == 'erro')
        
        cursor.close()
        conn.close()
        
        return {
            "total": total,
            "pendentes": pendentes,
            "processando": processando,
            "concluidos": concluidos,
            "erros": erros,
            "cnpjs": cnpjs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar CNPJs: {str(e)}")

@router.post("/reprocessar-erros", response_model=CNPJProcessingResponse)
async def reprocessar_erros_excel(
    texto_erro: Optional[str] = Query(None, description="Filtrar por texto específico de erro (ex: 'PDF não encontrado')"),
    dias: Optional[int] = Query(7, description="Processar erros dos últimos X dias")
):
    """
    Reprocessar CNPJs com erro (especialmente aqueles com erro de PDF não encontrado)
    
    Args:
        texto_erro: Filtrar por texto específico no erro
        dias: Processar erros dos últimos X dias (padrão: 7)
        
    Returns:
        Resultado da operação com o número total de CNPJs reenfileirados
    """
    try:
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Construir consulta SQL com filtros
        query = "SELECT * FROM fila_cnpj WHERE status = 'erro'"
        params = []
        
        # Filtrar por texto de erro específico
        if texto_erro:
            query += " AND resultado LIKE %s"
            params.append(f"%{texto_erro}%")
        
        # Filtrar por data
        if dias:
            data_inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
            query += " AND DATE(data_criacao) >= %s"
            params.append(data_inicio)
        
        # Executar consulta
        cursor.execute(query, params)
        erros_rows = cursor.fetchall()
        
        if not erros_rows:
            return CNPJProcessingResponse(
                total_processed=0,
                cnpjs=[]
            )
        
        # Reprocessar cada CNPJ com erro
        reprocessed_count = 0
        for row in erros_rows:
            cnpj_obj = CNPJ(
                cnpj=row['cnpj'],
                razao_social=row['nome'],
                municipio=row['municipio']
            )
            
            # Atualizar o status para pendente
            cursor.execute(
                "UPDATE fila_cnpj SET status = %s, resultado = %s WHERE id = %s",
                ("pendente", "", row['id'])
            )
            
            # Enviar para a fila
            # Nota: não usamos send_to_queue_and_db que criaria uma nova entrada
            # Em vez disso, enviamos diretamente o ID existente para a fila
            try:
                import pika
                # Usar a mesma lógica para obter RABBITMQ_HOST que está no queue_service
                from app.services.queue_service import RABBITMQ_HOST
                connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
                channel = connection.channel()
                channel.queue_declare(queue='fila_cnpj')
                channel.basic_publish(
                    exchange='',
                    routing_key='fila_cnpj',
                    body=str(row['id'])
                )
                connection.close()
                reprocessed_count += 1
            except Exception as e:
                # Se falhar ao enviar para a fila, reverter o status para erro
                cursor.execute(
                    "UPDATE fila_cnpj SET status = %s, resultado = %s WHERE id = %s",
                    ("erro", f"Erro ao reprocessar: {str(e)}", row['id'])
                )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return CNPJProcessingResponse(
            total_processed=reprocessed_count,
            cnpjs=[]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs com erro: {str(e)}")

@router.api_route("/reprocessar-erros-recriando", methods=["GET", "POST"], response_model=CNPJProcessingResponse)
async def reprocessar_erros_recriando(
    limite: int = Query(100, description="Número máximo de CNPJs com erro a reprocessar")
):
    """
    Reprocessar todos os CNPJs com status de erro, excluindo-os do banco antes de reprocessar
    
    Args:
        limite: Número máximo de CNPJs a reprocessar
        
    Returns:
        Resultado da operação
    """
    try:
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Construir consulta SQL com filtros
        query = "SELECT * FROM fila_cnpj WHERE status = 'erro'"
        params = []
        
        # Limitar número de registros
        if limite:
            query += " LIMIT %s"
            params.append(limite)
        
        # Executar consulta
        cursor.execute(query, params)
        erros_rows = cursor.fetchall()
        
        if not erros_rows:
            return CNPJProcessingResponse(
                total_processed=0,
                cnpjs=[]
            )
        
        # Armazenar IDs para exclusão
        ids_para_excluir = []
        for row in erros_rows:
            if 'id' in row and row['id']:
                ids_para_excluir.append(row['id'])
        
        cnpjs_processados = []
        
        # Reprocessar cada CNPJ com erro, criando novo registro
        for row in erros_rows:
            try:
                # Extrair os dados do CNPJ com tratamento para evitar KeyError
                cnpj_str = row.get('cnpj', '')
                razao_social = row.get('razao_social', '') or row.get('nome', 'Empresa')
                municipio = row.get('municipio', '')
                
                # Criar objeto CNPJ corretamente
                cnpj_obj = CNPJ(
                    cnpj=cnpj_str,
                    razao_social=razao_social,
                    municipio=municipio
                )
                
                # Enviar para a fila e criar novo registro
                new_id = send_to_queue_and_db(cnpj_obj)
                
                cnpjs_processados.append({
                    "nome": razao_social,
                    "cnpj": cnpj_obj.cnpj,
                    "cnpj_formatado": CNPJService.format_cnpj(cnpj_obj.cnpj),
                    "razao_social": razao_social,
                    "municipio": municipio,
                    "old_id": row.get('id', 0),
                    "new_id": new_id,
                    "interaction_result": {
                        "status": "queued",
                        "message": f"CNPJ {CNPJService.format_cnpj(cnpj_obj.cnpj)} foi enviado para processamento"
                    },
                    "screenshots": []
                })
            except Exception as item_error:
                print(f"Erro ao processar item específico: {item_error}")
        
        # Excluir registros antigos
        if ids_para_excluir:
            placeholders = ", ".join(["%s"] * len(ids_para_excluir))
            cursor.execute(
                f"DELETE FROM fila_cnpj WHERE id IN ({placeholders})",
                ids_para_excluir
            )
            conn.commit()
            print(f"Excluídos {len(ids_para_excluir)} registros antigos com erro")
        else:
            print("Nenhum registro encontrado para exclusão")
        
        cursor.close()
        conn.close()
        
        return CNPJProcessingResponse(
            total_processed=len(cnpjs_processados),
            cnpjs=cnpjs_processados
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs com erro: {str(e)}")

@router.api_route("/reprocessar-cnpj-individual", methods=["GET", "POST"], response_model=CNPJProcessingResponse)
async def reprocessar_cnpj_individual(
    cnpj_id: int = Query(..., description="ID do CNPJ na tabela fila_cnpj"),
    deletar_registro: bool = Query(True, description="Se True, exclui o registro do banco antes de reprocessar")
):
    """
    Reprocessar um CNPJ específico, opcionalmente excluindo o registro anterior
    
    Args:
        cnpj_id: ID do CNPJ na tabela fila_cnpj
        deletar_registro: Se True, exclui o registro do banco antes de reprocessar
        
    Returns:
        Resultado da operação
    """
    try:
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Buscar o CNPJ pelo ID
        cursor.execute(
            "SELECT * FROM fila_cnpj WHERE id = %s",
            (cnpj_id,)
        )
        cnpj_row = cursor.fetchone()
        
        if not cnpj_row:
            raise HTTPException(
                status_code=404,
                detail=f"CNPJ com ID {cnpj_id} não encontrado"
            )
        
        # Criar objeto CNPJ
        cnpj_obj = CNPJ(
            cnpj=cnpj_row['cnpj'],
            razao_social=cnpj_row.get('razao_social', '') or cnpj_row.get('nome', 'Empresa'),
            municipio=cnpj_row.get('municipio', '')
        )
        
        # Se solicitado, excluir o registro existente
        if deletar_registro:
            cursor.execute(
                "DELETE FROM fila_cnpj WHERE id = %s",
                (cnpj_id,)
            )
            conn.commit()
            
        # Enviar para a fila e criar novo registro
        new_id = send_to_queue_and_db(cnpj_obj)
        
        cursor.close()
        conn.close()
        
        # Formatar o CNPJ para retorno
        cnpj_formatado = CNPJService.format_cnpj(cnpj_obj.cnpj)
        
        return CNPJProcessingResponse(
            total_processed=1,
            cnpjs=[{
                "nome": cnpj_obj.razao_social or "Empresa",
                "cnpj": cnpj_obj.cnpj,
                "cnpj_formatado": cnpj_formatado,
                "razao_social": cnpj_obj.razao_social,
                "municipio": cnpj_obj.municipio,
                "status": "pending",
                "new_id": new_id,
                "interaction_result": {
                    "status": "queued",
                    "message": f"CNPJ {cnpj_formatado} foi enviado para processamento"
                },
                "screenshots": []
            }]
        )
    
    except HTTPException as he:
        # Re-raise HTTP exceptions without wrapping
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJ individual: {str(e)}") 