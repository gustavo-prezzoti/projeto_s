from typing import List, Dict, Any, Optional
import pandas as pd
from app.models.excel_data import ExcelData, ExcelRow

class ExcelService:
    @staticmethod
    async def process_excel_file(file_path: str, sheet_name: Optional[str] = None) -> ExcelData:
        """
        Process an Excel file and return structured data
        
        Args:
            file_path: Path to the uploaded Excel file
            sheet_name: Name of the sheet to process (if None, uses the first sheet)
            
        Returns:
            ExcelData object containing the parsed data
        """
        # Read the Excel file
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        else:
            # Get the first sheet if none specified
            xl = pd.ExcelFile(file_path)
            sheet_name = xl.sheet_names[0]
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
        # Rename columns to match expected format if needed
        # Check if we have the expected columns based on the sample file
        if "RAZÃO_SOCIAL" in df.columns and "No. DO CNPJ" in df.columns:
            # Formato esperado com RAZÃO_SOCIAL
            pass
        elif "NOME DO CLIENTE" in df.columns and "No. DO CNPJ" in df.columns:
            # O formato antigo com NOME DO CLIENTE
            pass
        elif len(df.columns) >= 2:
            # If the file has at least 2 columns but not with our expected names,
            # rename them to match our expected format
            # This is based on the sample where the first column is the name and the second is the CNPJ
            new_columns = list(df.columns)
            new_columns[0] = "RAZÃO_SOCIAL"  # Preferir usar RAZÃO_SOCIAL como default
            if len(new_columns) > 1:
                new_columns[1] = "No. DO CNPJ"
            df.columns = new_columns
        
        # Convert to list of dictionaries
        rows = []
        for _, row in df.iterrows():
            # Clean NaN values
            row_dict = row.to_dict()
            cleaned_dict = {k: "" if pd.isna(v) else v for k, v in row_dict.items()}
            rows.append(ExcelRow(data=cleaned_dict))
            
        # Get just the filename, not the full path
        filename = file_path.split("/")[-1].split("\\")[-1]
        
        return ExcelData(
            filename=filename,
            sheet_name=sheet_name,
            rows=rows
        ) 