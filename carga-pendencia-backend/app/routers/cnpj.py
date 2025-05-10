from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends, Path, status, Body
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
from app.services.queue_service import send_to_queue_and_db, MYSQL_HOST, check_cnpj_exists, get_all_cnpjs, delete_from_queue_by_id
from app.models.cnpj import CNPJ
from app.schemas.requests import GetCNPJRequest, BatchDeleteRequest
from app.schemas.responses import ListCNPJResponse
from app.routers.auth import get_current_user

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
    cnpjs: List[str],
    current_user: dict = Depends(get_current_user)
):
    """
    Process a list of selected CNPJs from the validation result
    
    Args:
        cnpjs: List of CNPJ strings to process
        current_user: Current authenticated user
        
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
        
        # Obter user_id do token
        user_id = current_user.get("user_id")
        print(f"User ID do token: {user_id}")
        
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
            
            # Send to queue and DB with user_id
            print(f"Sending CNPJ to queue and DB with user_id {user_id}: {cleaned_cnpj}")
            send_to_queue_and_db(cnpj_obj, user_id=user_id)
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
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload an Excel file with CNPJ data, process it, and interact with the website.
    Will always delete existing records and create new ones.
    
    Args:
        file: The Excel file containing CNPJ data
        current_user: Current authenticated user
        
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
        
        # Extrair user_id do token
        user_id = current_user.get("user_id")
        print(f"User ID from token: {user_id}")
        
        if not user_id:
            print("WARNING: No user_id found in token, CNPJs will not be associated with a user")
        
        # Excluir registros existentes para cada CNPJ (apenas os do usuário atual)
        for cnpj in cnpjs_to_process:
            if user_id:
                cursor.execute(
                    "SELECT id FROM fila_cnpj WHERE cnpj = %s AND (user_id = %s OR user_id IS NULL)",
                    (cnpj.cnpj, user_id)
                )
            else:
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
                
        # Enfileira cada CNPJ e registra no banco (com user_id)
        for cnpj in cnpjs_to_process:
            print(f"Sending CNPJ to queue with user_id {user_id}: {cnpj.cnpj}")
            send_to_queue_and_db(cnpj, user_id=user_id)
            
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
async def reprocess_pending_cnpjs(
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar todos os CNPJs com status 'pendente' ou 'erro' no banco de dados
    
    Returns:
        Resultado da operação com o número total de CNPJs reenfileirados
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Buscar todos os CNPJs pendentes ou com erro do usuário atual
        if user_id:
            cursor.execute(
                "SELECT * FROM fila_cnpj WHERE status IN ('pendente', 'erro') AND user_id = %s",
                (user_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM fila_cnpj WHERE status IN ('pendente', 'erro')"
            )
            
        pending_rows = cursor.fetchall()
        
        if not pending_rows:
            return CNPJProcessingResponse(
                total_processed=0,
                cnpjs=[]
            )
        
        # Armazenar IDs para exclusão
        ids_para_excluir = []
        for row in pending_rows:
            if 'id' in row and row['id']:
                ids_para_excluir.append(row['id'])
        
        cnpjs_processados = []
        
        # Reprocessar cada CNPJ pendente, criando novo registro
        for row in pending_rows:
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
                
                # Preservar o user_id original ou usar o atual
                row_user_id = row.get('user_id') or user_id
                
                # Enviar para a fila e criar novo registro
                new_id = send_to_queue_and_db(cnpj_obj, user_id=row_user_id)
                
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
            print(f"Excluídos {len(ids_para_excluir)} registros antigos")
        else:
            print("Nenhum registro encontrado para exclusão")
        
        cursor.close()
        conn.close()
        
        return CNPJProcessingResponse(
            total_processed=len(cnpjs_processados),
            cnpjs=cnpjs_processados
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs pendentes: {str(e)}")

@router.post("/reprocessar-erros", response_model=CNPJProcessingResponse)
async def reprocessar_erros_excel(
    texto_erro: Optional[str] = Query(None, description="Filtrar por texto específico de erro (ex: 'PDF não encontrado')"),
    dias: Optional[int] = Query(7, description="Processar erros dos últimos X dias"),
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar CNPJs com erro (especialmente aqueles com erro de PDF não encontrado)
    
    Args:
        texto_erro: Filtrar por texto específico no erro
        dias: Processar erros dos últimos X dias (padrão: 7)
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação com o número total de CNPJs reenfileirados
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
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
        
        # Filtrar por user_id se disponível
        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)
        
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
                
                # Preservar o user_id original ou usar o atual
                row_user_id = row.get('user_id') or user_id
                
                # Enviar para a fila e criar novo registro
                new_id = send_to_queue_and_db(cnpj_obj, user_id=row_user_id)
                
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

@router.api_route("/reprocessar-erros-recriando", methods=["GET", "POST"], response_model=CNPJProcessingResponse)
async def reprocessar_erros_recriando(
    limite: int = Query(100, description="Número máximo de CNPJs com erro a reprocessar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar todos os CNPJs com status de erro, excluindo-os do banco antes de reprocessar
    
    Args:
        limite: Número máximo de CNPJs a reprocessar
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
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
        
        # Filtrar por user_id se disponível
        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)
        
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
                
                # Preservar o user_id original ou usar o atual
                row_user_id = row.get('user_id') or user_id
                
                # Enviar para a fila e criar novo registro
                new_id = send_to_queue_and_db(cnpj_obj, user_id=row_user_id)
                
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
    deletar_registro: bool = Query(True, description="Se True, exclui o registro do banco antes de reprocessar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar um CNPJ específico, opcionalmente excluindo o registro anterior
    
    Args:
        cnpj_id: ID do CNPJ na tabela fila_cnpj
        deletar_registro: Se True, exclui o registro do banco antes de reprocessar
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
        # Conectar ao banco de dados
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user="root",
            password="root",
            database="relatorio_pendencia"
        )
        cursor = conn.cursor(dictionary=True)

        # Buscar o CNPJ pelo ID (e verificar se pertence ao usuário atual)
        if user_id:
            cursor.execute(
                "SELECT * FROM fila_cnpj WHERE id = %s AND (user_id = %s OR user_id IS NULL)",
                (cnpj_id, user_id)
            )
        else:
            cursor.execute(
                "SELECT * FROM fila_cnpj WHERE id = %s",
                (cnpj_id,)
            )
            
        cnpj_row = cursor.fetchone()
        
        if not cnpj_row:
            raise HTTPException(
                status_code=404,
                detail=f"CNPJ com ID {cnpj_id} não encontrado ou você não tem permissão para reprocessá-lo"
            )
        
        # Criar objeto CNPJ
        cnpj_obj = CNPJ(
            cnpj=cnpj_row['cnpj'],
            razao_social=cnpj_row.get('razao_social', '') or cnpj_row.get('nome', 'Empresa'),
            municipio=cnpj_row.get('municipio', '')
        )
        
        # Preservar o user_id original ou usar o atual
        row_user_id = cnpj_row.get('user_id') or user_id
        
        # Se solicitado, excluir o registro existente
        if deletar_registro:
            cursor.execute(
                "DELETE FROM fila_cnpj WHERE id = %s",
                (cnpj_id,)
            )
            conn.commit()
            
        # Enviar para a fila e criar novo registro
        new_id = send_to_queue_and_db(cnpj_obj, user_id=row_user_id)
        
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

@router.get("/list", response_model=List[ListCNPJResponse])
async def list_cnpjs(current_user: dict = Depends(get_current_user)):
    """
    Lista todos os CNPJs do usuário atual
    """
    try:
        # Obter todos os CNPJs do usuário atual
        cnpjs = get_all_cnpjs(user_id=current_user.get("user_id"))
        return cnpjs
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar CNPJs: {str(e)}"
        )

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload de arquivo Excel com CNPJs para processamento
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Arquivo deve ser .xlsx ou .xls"
        )
    
    try:
        # Processar o arquivo Excel
        excel_data = ExcelService.process_excel_file(await file.read())
        
        # Extrair CNPJs do Excel
        cnpjs = CNPJService.extract_cnpjs_from_excel_data(excel_data)
        
        if not cnpjs:
            raise HTTPException(
                status_code=400,
                detail="Nenhum CNPJ válido encontrado no arquivo"
            )
        
        # Verificar duplicatas no Excel
        duplicates = CNPJService.find_duplicates_in_excel(cnpjs)
        
        # Remover duplicatas
        unique_cnpjs = CNPJService.get_unique_cnpjs(cnpjs)
        
        # Verificar CNPJs que já existem no banco
        new_cnpjs, existing_cnpjs = CNPJService.validate_cnpjs_against_db(unique_cnpjs)
        
        # Enviar novos CNPJs para a fila e banco
        for cnpj in new_cnpjs:
            send_to_queue_and_db(cnpj, user_id=current_user.get("user_id"))
        
        return {
            "message": "Arquivo processado com sucesso",
            "total_cnpjs": len(cnpjs),
            "unique_cnpjs": len(unique_cnpjs),
            "new_cnpjs": len(new_cnpjs),
            "existing_cnpjs": len(existing_cnpjs),
            "duplicate_cnpjs": len(duplicates),
            "duplicates": [{"cnpj": k, "count": len(v)} for k, v in duplicates.items()]
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Erro no processamento: {str(e)}"
        )

@router.post("/add")
async def add_single_cnpj(
    cnpj_data: GetCNPJRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Adiciona um único CNPJ para processamento
    """
    try:
        # Verifica se já existe no banco
        exists, record = check_cnpj_exists(cnpj_data.cnpj)
        if exists:
            return {
                "message": "CNPJ já existe na fila",
                "cnpj": cnpj_data.cnpj,
                "record": record
            }
        
        # Cria objeto CNPJ
        cnpj_obj = CNPJ(
            cnpj=cnpj_data.cnpj,
            razao_social=cnpj_data.razao_social or "",
            municipio=cnpj_data.municipio or ""
        )
        
        # Envia para fila e banco
        fila_id = send_to_queue_and_db(cnpj_obj, user_id=current_user.get("user_id"))
        
        return {
            "message": "CNPJ adicionado com sucesso",
            "cnpj": cnpj_data.cnpj,
            "fila_id": fila_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao adicionar CNPJ: {str(e)}"
        )

@router.delete("/delete-batch", status_code=status.HTTP_200_OK)
async def batch_delete_cnpjs(
    request: BatchDeleteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Remove múltiplos CNPJs da fila pelos IDs
    
    Args:
        request: Requisição contendo lista de IDs a serem excluídos
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação com detalhes de quais IDs foram excluídos e quais falharam
    """
    try:
        user_id = current_user.get("user_id")
        
        if not request.fila_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum ID fornecido para exclusão"
            )
        
        results = {
            "total": len(request.fila_ids),
            "deleted": 0,
            "failed": 0,
            "failed_ids": []
        }
        
        for fila_id in request.fila_ids:
            deleted = delete_from_queue_by_id(fila_id, user_id=user_id)
            if deleted:
                results["deleted"] += 1
            else:
                results["failed"] += 1
                results["failed_ids"].append(fila_id)
        
        if results["failed"] > 0 and results["deleted"] == 0:
            # Se todos os registros falharem, retornar erro
            return {
                "status": "error",
                "message": "Nenhum registro pôde ser excluído. Verifique se os IDs são válidos e pertencem ao seu usuário.",
                "details": results
            }
        
        return {
            "status": "success",
            "message": f"Excluídos {results['deleted']} de {results['total']} registros com sucesso.",
            "details": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir registros em lote: {str(e)}"
        )

@router.delete("/{fila_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cnpj(
    fila_id: int = Path(..., description="ID do registro na fila"),
    current_user: dict = Depends(get_current_user)
):
    """
    Remove um CNPJ da fila pelo ID
    """
    deleted = delete_from_queue_by_id(fila_id, user_id=current_user.get("user_id"))
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CNPJ não encontrado ou você não tem permissão para excluí-lo"
        )
    
    return None  # 204 No Content 