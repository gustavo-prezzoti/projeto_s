from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import os
import shutil
from uuid import uuid4

from app.models.excel_data import ExcelData
from app.services.excel_service import ExcelService

router = APIRouter(prefix="/excel", tags=["Excel Upload"])

@router.post("/upload", response_model=ExcelData)
async def upload_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None)
):
    """
    Upload an Excel file and parse its content
    
    Args:
        file: The Excel file to upload
        sheet_name: Name of the sheet to process (optional)
        
    Returns:
        Parsed data from the Excel file
    """
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
    
    try:
        # Process the Excel file
        result = await ExcelService.process_excel_file(temp_file_path, sheet_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        # Clean up the temp file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path) 