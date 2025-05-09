from pydantic import BaseModel
from typing import Optional
 
class ExcelUploadRequest(BaseModel):
    sheet_name: Optional[str] = None 