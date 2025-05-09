from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from pathlib import Path
from typing import List

router = APIRouter(prefix="/utils", tags=["Utilities"])

@router.get("/screenshots", response_model=List[str])
async def list_screenshots():
    """List all available screenshots"""
    screenshots_dir = Path("screenshots")
    
    if not screenshots_dir.exists():
        return []
    
    screenshots = [str(file) for file in screenshots_dir.glob("*.png")]
    return screenshots

@router.get("/screenshots/{filename}")
async def get_screenshot(filename: str):
    """Get a specific screenshot"""
    file_path = Path(f"screenshots/{filename}")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    
    return FileResponse(str(file_path)) 