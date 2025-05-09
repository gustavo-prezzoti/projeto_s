from pydantic import BaseModel
from typing import Optional, Dict, Any

class CNPJ(BaseModel):
    """Represents parsed CNPJ information"""
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None 