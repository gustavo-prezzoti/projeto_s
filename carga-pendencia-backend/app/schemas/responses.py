from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class CNPJResponse(BaseModel):
    """Response for a single CNPJ processed"""
    nome: str
    cnpj: str
    cnpj_formatado: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    interaction_result: Dict[str, Any]
    screenshots: List[str] = []

class CNPJProcessingResponse(BaseModel):
    """Response for CNPJ processing endpoint"""
    total_processed: int
    cnpjs: List[CNPJResponse]

class CNPJValidationItem(BaseModel):
    """Item in the validation response for a single CNPJ"""
    nome: str
    cnpj: str
    cnpj_formatado: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    status: str
    existing: bool
    duplicate_in_file: bool = False
    duplicate_count: int = 0
    db_record: Optional[Dict[str, Any]] = None

class ExcelValidationResponse(BaseModel):
    """Response for Excel validation endpoint"""
    total: int
    new_items: int
    existing_items: int
    duplicate_items: int
    cnpjs: List[CNPJValidationItem]

class ListCNPJResponse(BaseModel):
    """
    Resposta para listagem de CNPJs na fila
    """
    id: int
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    status: str
    resultado: Optional[str] = None
    status_divida: Optional[str] = None
    pdf_path: Optional[str] = None
    data_criacao: str
    data_atualizacao: Optional[str] = None
    user_id: Optional[int] = None
    full_result: Optional[str] = None 