from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends, Path, status, Body
from typing import Optional, List, Dict, Any
import os
import shutil
from uuid import uuid4
import asyncio
from concurrent.futures import ThreadPoolExecutor
import tempfile
from datetime import datetime, timedelta
import re

from app.services.excel_service import ExcelService
from app.services.cnpj_service import CNPJService
from app.schemas.responses import CNPJProcessingResponse, CNPJResponse, ExcelValidationResponse, CNPJValidationItem
from app.services.queue_service import send_to_queue_and_db, check_cnpj_exists, get_all_cnpjs, delete_from_queue_by_id
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
            
        # Extrair user_id do token
        user_id = current_user.get("user_id")
        print(f"User ID from token: {user_id}")
        
        if not user_id:
            print("WARNING: No user_id found in token, CNPJs will not be associated with a user")
        
        # Para cada CNPJ, verificar se já existe e excluir se existir
        deleted_records = 0
        print("Will delete existing records before processing")
        
        for cnpj in cnpjs_to_process:
            # Verificar se CNPJ existe
            exists, record = check_cnpj_exists(cnpj.cnpj)
            if exists and record:
                # Verificar se pertence ao usuário atual
                if user_id is None or user_id == record.get("user_id") or record.get("user_id") is None:
                    # Excluir o registro
                    if delete_from_queue_by_id(record.get("id")):
                        deleted_records += 1
                        print(f"Deleted existing record for CNPJ {cnpj.cnpj}")
        
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
        
        # Obter todos os CNPJs do usuário atual com status pendente ou erro
        all_cnpjs = get_all_cnpjs(user_id)
        
        # Filtrar apenas os pendentes ou com erro
        pending_rows = [row for row in all_cnpjs if row.get('status') in ('pendente', 'erro')]
        
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
        for fila_id in ids_para_excluir:
            try:
                delete_from_queue_by_id(fila_id, user_id)
                print(f"Registro antigo {fila_id} excluído com sucesso")
            except Exception as e:
                print(f"Erro ao excluir registro antigo {fila_id}: {e}")
        
        print(f"Excluídos {len(ids_para_excluir)} registros antigos")
        
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
        
        # Obter todos os CNPJs do usuário com status de erro
        all_cnpjs = get_all_cnpjs(user_id)
        
        # Filtrar apenas os que têm status 'erro'
        erros_rows = [row for row in all_cnpjs if row.get('status') == 'erro']
        
        # Filtrar por texto de erro específico
        if texto_erro:
            erros_rows = [row for row in erros_rows if texto_erro.lower() in (row.get('resultado', '') or '').lower()]
        
        # Filtrar por data
        if dias:
            data_limite = datetime.now() - timedelta(days=dias)
            # Converter para string para comparação mais simples
            data_limite_str = data_limite.strftime("%Y-%m-%d")
            
            # Filtrar resultados onde data_criacao é maior que data_limite
            erros_rows = [
                row for row in erros_rows 
                if row.get('data_criacao') and str(row.get('data_criacao')).split('T')[0] >= data_limite_str
            ]
        
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
        for fila_id in ids_para_excluir:
            delete_from_queue_by_id(fila_id, user_id)
            print(f"Registro antigo {fila_id} excluído com sucesso")
        
        return CNPJProcessingResponse(
            total_processed=len(cnpjs_processados),
            cnpjs=cnpjs_processados
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs com erro: {str(e)}")

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

@router.get("/reprocessar-erros-recriando", response_model=CNPJProcessingResponse)
async def reprocessar_erros_recriando(
    texto_erro: Optional[str] = Query(None, description="Filtrar por texto específico de erro (ex: 'PDF não encontrado')"),
    dias: Optional[int] = Query(7, description="Processar erros dos últimos X dias"),
    limite: Optional[int] = Query(100, description="Limite máximo de registros para processar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar CNPJs com erro, recriando-os no banco de dados e na fila
    
    Args:
        texto_erro: Filtrar por texto específico no erro
        dias: Processar erros dos últimos X dias (padrão: 7)
        limite: Número máximo de registros a processar (padrão: 100)
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação com o número total de CNPJs reenfileirados
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
        # Obter todos os CNPJs do usuário com status de erro
        all_cnpjs = get_all_cnpjs(user_id)
        
        # Registrar no log para debug
        print(f"Total de CNPJs encontrados: {len(all_cnpjs)}")
        
        # Filtrar apenas os que têm status 'erro' - garantindo comparação case-insensitive
        erros_rows = [row for row in all_cnpjs if str(row.get('status', '')).lower() == 'erro']
        print(f"CNPJs com status 'erro': {len(erros_rows)}")
        
        # Filtrar por texto de erro específico
        if texto_erro:
            erros_rows = [row for row in erros_rows if texto_erro.lower() in (row.get('resultado', '') or '').lower()]
            print(f"CNPJs com texto de erro '{texto_erro}': {len(erros_rows)}")
        
        # Filtrar por data - somente se o parâmetro dias for fornecido e maior que 0
        if dias and dias > 0:
            try:
                from datetime import datetime, timedelta
                
                # Calcular data limite - considerando hoje como ponto de referência
                data_limite = datetime.now() - timedelta(days=dias)
                data_limite_str = data_limite.strftime("%Y-%m-%d")
                print(f"Data limite: {data_limite_str}")
                
                # Lista temporária para armazenar registros filtrados por data
                registros_apos_data = []
                
                for row in erros_rows:
                    # Verificar se o registro tem data de criação
                    if not row.get('data_criacao'):
                        # Se não tiver data, incluir (melhor erro por excesso que por omissão)
                        registros_apos_data.append(row)
                        continue
                    
                    # Obter a data de criação como string
                    data_str = str(row.get('data_criacao'))
                    
                    # Verificar o formato da data (pode ter 'T' como separador)
                    if 'T' in data_str:
                        data_str = data_str.split('T')[0]  # Pegar apenas a parte da data (YYYY-MM-DD)
                    
                    # Se a data de criação for posterior à data limite, incluir o registro
                    if data_str >= data_limite_str:
                        registros_apos_data.append(row)
                
                # Atualizar a lista de erros
                erros_rows = registros_apos_data
                print(f"CNPJs após filtro de data (dos últimos {dias} dias): {len(erros_rows)}")
                
            except Exception as date_error:
                print(f"Erro ao filtrar por data: {date_error}")
                # Se houver erro no filtro de data, continue com todos os registros
        
        # Limitar número de registros a processar
        if limite and len(erros_rows) > limite:
            erros_rows = erros_rows[:limite]
            print(f"Limitando a {limite} registros")
        
        if not erros_rows:
            print("Nenhum CNPJ encontrado para reprocessamento")
            return CNPJProcessingResponse(
                total_processed=0,
                cnpjs=[]
            )
        
        print(f"Total de CNPJs para reprocessamento: {len(erros_rows)}")
        
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
                print(f"CNPJ {cnpj_str} reenfileirado com sucesso, novo ID: {new_id}")
            except Exception as item_error:
                print(f"Erro ao processar item específico: {item_error}")
        
        # Excluir registros antigos
        for fila_id in ids_para_excluir:
            try:
                deleted = delete_from_queue_by_id(fila_id, user_id)
                if deleted:
                    print(f"Registro antigo {fila_id} excluído com sucesso")
                else:
                    print(f"Não foi possível excluir o registro {fila_id}")
            except Exception as del_error:
                print(f"Erro ao excluir registro {fila_id}: {str(del_error)}")
        
        return CNPJProcessingResponse(
            total_processed=len(cnpjs_processados),
            cnpjs=cnpjs_processados
        )
    
    except Exception as e:
        import traceback
        print(f"Erro ao reprocessar CNPJs com erro: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJs com erro: {str(e)}")

@router.get("/reprocessar-cnpj-individual", response_model=CNPJProcessingResponse)
async def reprocessar_cnpj_individual(
    cnpj_id: int = Query(..., description="ID do registro do CNPJ a ser reprocessado"),
    deletar_registro: bool = Query(False, description="Se o registro original deve ser excluído após reprocessar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Reprocessar um único CNPJ pelo seu ID
    
    Args:
        cnpj_id: ID do registro do CNPJ na tabela fila_cnpj
        deletar_registro: Se True, o registro original será excluído após criar um novo
        current_user: Usuário autenticado atual
        
    Returns:
        Resultado da operação com detalhes do CNPJ reprocessado
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
        # Obter os dados do CNPJ pelo ID
        all_cnpjs = get_all_cnpjs(user_id)
        
        # Encontrar o registro específico
        cnpj_record = None
        for record in all_cnpjs:
            if record.get('id') == cnpj_id:
                cnpj_record = record
                break
        
        if not cnpj_record:
            raise HTTPException(
                status_code=404,
                detail=f"CNPJ com ID {cnpj_id} não encontrado ou você não tem permissão para acessá-lo"
            )
        
        # Extrair os dados do CNPJ
        cnpj_str = cnpj_record.get('cnpj', '')
        razao_social = cnpj_record.get('razao_social', '') or cnpj_record.get('nome', 'Empresa')
        municipio = cnpj_record.get('municipio', '')
        
        # Verificar se o CNPJ tem um formato válido
        if not cnpj_str or len(re.sub(r'[^\d]', '', cnpj_str)) != 14:
            raise HTTPException(
                status_code=400,
                detail=f"CNPJ inválido: {cnpj_str}"
            )
        
        # Criar objeto CNPJ
        cnpj_obj = CNPJ(
            cnpj=cnpj_str,
            razao_social=razao_social,
            municipio=municipio
        )
        
        # Preservar o user_id original ou usar o atual
        row_user_id = cnpj_record.get('user_id') or user_id
        
        # Enviar para a fila e criar novo registro
        new_id = send_to_queue_and_db(cnpj_obj, user_id=row_user_id)
        
        # Se solicitado, excluir o registro original
        if deletar_registro:
            delete_from_queue_by_id(cnpj_id, user_id)
            print(f"Registro original {cnpj_id} excluído com sucesso")
        
        # Preparar resposta
        return CNPJProcessingResponse(
            total_processed=1,
            cnpjs=[{
                "nome": razao_social,
                "cnpj": cnpj_obj.cnpj,
                "cnpj_formatado": CNPJService.format_cnpj(cnpj_obj.cnpj),
                "razao_social": razao_social,
                "municipio": municipio,
                "old_id": cnpj_id,
                "new_id": new_id,
                "interaction_result": {
                    "status": "queued",
                    "message": f"CNPJ {CNPJService.format_cnpj(cnpj_obj.cnpj)} foi enviado para processamento"
                },
                "screenshots": []
            }]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar CNPJ: {str(e)}")

@router.get("/listar-erros", response_model=List[ListCNPJResponse])
async def listar_erros(current_user: dict = Depends(get_current_user)):
    """
    Lista todos os CNPJs do usuário atual que têm status 'erro'
    """
    try:
        # Obter todos os CNPJs do usuário atual
        cnpjs = get_all_cnpjs(user_id=current_user.get("user_id"))
        
        # Filtrar apenas os que têm status 'erro'
        erros = [item for item in cnpjs if item.get('status') == 'erro']
        
        print(f"Encontrados {len(erros)} CNPJs com status 'erro'")
        
        return erros
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar CNPJs com erro: {str(e)}"
        )

@router.get("/debug-reprocessar-erros")
async def debug_reprocessar_erros(
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint de diagnóstico para verificar por que o reprocessamento não está funcionando
    """
    try:
        # Obter user_id do token
        user_id = current_user.get("user_id")
        
        # Obter todos os CNPJs do usuário
        all_cnpjs = get_all_cnpjs(user_id)
        
        # Contar por status
        status_counts = {}
        for item in all_cnpjs:
            status = item.get('status', 'unknown')
            if status in status_counts:
                status_counts[status] += 1
            else:
                status_counts[status] = 1
        
        # Verificar se há CNPJs com status 'erro'
        erros_rows = [row for row in all_cnpjs if row.get('status') == 'erro']
        
        # Ver datas dos erros
        datas = []
        for row in erros_rows[:5]:  # Mostrar até 5 exemplos
            if 'data_criacao' in row and row['data_criacao']:
                datas.append(str(row['data_criacao']))
        
        return {
            "total_cnpjs": len(all_cnpjs),
            "status_counts": status_counts,
            "erros_encontrados": len(erros_rows),
            "exemplos_datas": datas,
            "user_id": user_id
        }
    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        } 