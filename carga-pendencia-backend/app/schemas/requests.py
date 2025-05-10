from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ExcelUploadRequest(BaseModel):
    sheet_name: Optional[str] = None 

class GetCNPJRequest(BaseModel):
    """
    Requisição para adicionar um CNPJ para processamento
    """
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None 

class BatchDeleteRequest(BaseModel):
    """
    Requisição para excluir múltiplos CNPJs em lote
    """
    fila_ids: List[int] 