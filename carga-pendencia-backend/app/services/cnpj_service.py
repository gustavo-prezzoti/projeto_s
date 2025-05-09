import re
from typing import List, Dict, Any, Tuple
import pandas as pd
from app.models.cnpj import CNPJ
from app.services.excel_service import ExcelService
from app.models.excel_data import ExcelData
from app.services.web_service import WebService
from app.services.queue_service import check_cnpj_exists

class CNPJService:
    @staticmethod
    def extract_cnpjs_from_excel_data(excel_data: ExcelData) -> List[CNPJ]:
        """
        Extract CNPJ information from Excel data
        
        Args:
            excel_data: Processed Excel data
            
        Returns:
            List of CNPJ objects
        """
        cnpjs = []
        
        for row in excel_data.rows:
            data = row.data
            
            # Try to find CNPJ, razão social and município fields in the data
            cnpj_value = None
            nome_value = None
            razao_social_value = None
            municipio_value = None
            
            # Check for column names that might contain CNPJ, razão social and município
            for key, value in data.items():
                key_lower = str(key).lower()
                if any(term in key_lower for term in ["cnpj", "no. do cnpj", "no do cnpj", "número", "numero"]):
                    cnpj_value = str(value)
                elif any(term in key_lower for term in ["razão social", "razao social", "razão_social", "razao_social"]):
                    razao_social_value = str(value)
                elif any(term in key_lower for term in ["municipio", "município", "cidade"]):
                    municipio_value = str(value)
                elif any(term in key_lower for term in ["nome", "cliente", "nome do cliente"]):
                    nome_value = str(value)
            
            # Priorizar razão social sobre nome, se disponível
            if razao_social_value:
                nome_value = razao_social_value
            
            # Handle case where standard column detection didn't find values
            if not cnpj_value or not nome_value:
                # For the EmpresasFriburgocomCNPJ.xlsx format, we expect:
                # First column = NOME DO CLIENTE or RAZÃO_SOCIAL
                # Second column = No. DO CNPJ
                keys = list(data.keys())
                if len(keys) >= 2:
                    if not nome_value:
                        nome_value = str(data[keys[0]])
                    if not cnpj_value:
                        cnpj_value = str(data[keys[1]])
                    # Tentar encontrar município em outra coluna, se existir
                    if len(keys) >= 3 and not municipio_value:
                        municipio_value = str(data[keys[2]])
                        
            # Skip rows that still don't have both CNPJ and name
            if not cnpj_value or not nome_value:
                continue
                
            # Skip empty values
            if not cnpj_value.strip() or not nome_value.strip():
                continue
            
            # Clean CNPJ value (remove non-numeric characters)
            cleaned_cnpj = re.sub(r'[^\d]', '', cnpj_value)
            
            # Skip invalid CNPJs (too short or too long)
            if len(cleaned_cnpj) < 8 or len(cleaned_cnpj) > 14:
                continue
            
            # Pad with zeros if needed to get to 14 digits
            if len(cleaned_cnpj) < 14:
                cleaned_cnpj = cleaned_cnpj.zfill(14)
            
            cnpjs.append(CNPJ(
                cnpj=cleaned_cnpj,
                razao_social=razao_social_value or nome_value,
                municipio=municipio_value or "",
                raw_data=data
            ))
                
        return cnpjs
    
    @staticmethod
    def validate_cnpjs_against_db(cnpjs: List[CNPJ]) -> Tuple[List[CNPJ], List[Dict[str, Any]]]:
        """
        Validate a list of CNPJs against the database and return two lists:
        - New CNPJs that don't exist in the database
        - Existing CNPJs with their database records
        
        Args:
            cnpjs: List of CNPJ objects to validate
            
        Returns:
            Tuple containing (new_cnpjs, existing_cnpjs_with_records)
        """
        new_cnpjs = []
        existing_cnpjs = []
        
        if not cnpjs:
            print("Warning: Empty CNPJ list passed to validate_cnpjs_against_db")
            return new_cnpjs, existing_cnpjs
        
        try:
            for cnpj in cnpjs:
                try:
                    exists, record = check_cnpj_exists(cnpj.cnpj)
                    if exists and record:
                        existing_cnpjs.append({
                            "cnpj_obj": cnpj,
                            "db_record": record
                        })
                    else:
                        new_cnpjs.append(cnpj)
                except Exception as e:
                    print(f"Error checking CNPJ {cnpj.cnpj}: {str(e)}")
                    # On error checking a specific CNPJ, add it to new_cnpjs to be safe
                    new_cnpjs.append(cnpj)
        except Exception as e:
            import traceback
            print(f"Error in validate_cnpjs_against_db: {str(e)}")
            print(traceback.format_exc())
            # Return what we have so far rather than failing completely
        
        return new_cnpjs, existing_cnpjs
    
    @staticmethod
    def get_unique_cnpjs(cnpjs: List[CNPJ]) -> List[CNPJ]:
        """
        Filter a list of CNPJs to include only unique CNPJ numbers
        
        Args:
            cnpjs: List of CNPJ objects
            
        Returns:
            List of CNPJ objects with unique CNPJ numbers
        """
        unique_cnpjs = {}
        for cnpj in cnpjs:
            if cnpj.cnpj not in unique_cnpjs:
                unique_cnpjs[cnpj.cnpj] = cnpj
        
        return list(unique_cnpjs.values())
        
    @staticmethod
    def format_cnpj(cnpj_raw: str) -> str:
        """
        Format CNPJ string to standard format (XX.XXX.XXX/XXXX-XX)
        
        Args:
            cnpj_raw: Raw CNPJ string (only digits)
            
        Returns:
            Formatted CNPJ string
        """
        if len(cnpj_raw) != 14:
            return cnpj_raw
        
        return f"{cnpj_raw[0:2]}.{cnpj_raw[2:5]}.{cnpj_raw[5:8]}/{cnpj_raw[8:12]}-{cnpj_raw[12:14]}"
    
    @staticmethod
    async def process_cnpj_on_website(cnpj: CNPJ, headless: bool = False, fila_id: int = None, wait_times: dict = None) -> Dict[str, Any]:
        """
        Process a CNPJ on the specified website
        
        Args:
            cnpj: CNPJ object
            headless: Whether to run browser in headless mode
            fila_id: ID da fila para nomear o PDF
            wait_times: Tempos de espera calculados dinamicamente
            
        Returns:
            Dictionary with interaction results
        """
        # Format the CNPJ for display
        formatted_cnpj = CNPJService.format_cnpj(cnpj.cnpj)
        
        # Use the WebService to navigate to the portal, passando fila_id e wait_times
        web_result = await WebService.navigate_to_gpi_portal(cnpj.cnpj, headless, fila_id=fila_id, wait_times=wait_times)
        if web_result is None:
            web_result = {}
        
        # Garantir que o campo 'resultado' seja preservado explicitamente
        resultado = web_result.get("resultado", "")
        status_divida = web_result.get("status_divida", "")
        
        # Combine the results
        return {
            "resultado": resultado,  # Colocado explicitamente como primeiro campo
            "status_divida": status_divida,  # Garantir que este campo seja preservado
            "status": web_result.get("status", "unknown"),
            "message": f"Processed CNPJ {formatted_cnpj}",
            "website_url": web_result.get("url", "unknown"),
            "actions": web_result.get("actions", []),
            "screenshots": web_result.get("screenshots", []),
            "full_result": web_result.get("full_result", ""),
            "cnpj_data": {
                "raw": cnpj.cnpj,
                "formatted": formatted_cnpj,
                "razao_social": cnpj.razao_social,
                "municipio": cnpj.municipio
            }
        } 
    
    @staticmethod
    def find_duplicates_in_excel(cnpjs: List[CNPJ]) -> Dict[str, List[CNPJ]]:
        """
        Find duplicate CNPJs in Excel data
        
        Args:
            cnpjs: List of CNPJ objects extracted from Excel
            
        Returns:
            Dictionary with CNPJ numbers as keys and lists of duplicate CNPJ objects as values
        """
        if not cnpjs:
            print("Warning: Empty CNPJ list passed to find_duplicates_in_excel")
            return {}
            
        try:
            # Count occurrences of each CNPJ
            cnpj_count = {}
            for cnpj in cnpjs:
                if not cnpj or not hasattr(cnpj, 'cnpj'):
                    print(f"Warning: Invalid CNPJ object encountered: {cnpj}")
                    continue
                    
                try:
                    if cnpj.cnpj in cnpj_count:
                        cnpj_count[cnpj.cnpj].append(cnpj)
                    else:
                        cnpj_count[cnpj.cnpj] = [cnpj]
                except Exception as e:
                    print(f"Error processing CNPJ {getattr(cnpj, 'cnpj', 'unknown')}: {str(e)}")
            
            # Filter to include only duplicate CNPJs (more than one occurrence)
            duplicates = {cnpj: occurrences for cnpj, occurrences in cnpj_count.items() if len(occurrences) > 1}
            
            return duplicates
        except Exception as e:
            import traceback
            print(f"Error in find_duplicates_in_excel: {str(e)}")
            print(traceback.format_exc())
            return {} 