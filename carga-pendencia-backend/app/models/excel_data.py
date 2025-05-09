from typing import Dict, Any, List
from pydantic import BaseModel

class ExcelRow(BaseModel):
    """Represents a single row of data from an Excel file"""
    data: Dict[str, Any]

class ExcelData(BaseModel):
    """Represents the complete data loaded from an Excel file"""
    filename: str
    sheet_name: str
    rows: List[ExcelRow] 