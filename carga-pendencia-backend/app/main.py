import uvicorn
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys
import time
import atexit
import contextlib
import threading
import signal
import psutil
# Importar apenas o necessário para a rota de processar CNPJ
from app.routers import cnpj
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import excel
from app.routers import auth  # Novo roteador de autenticação

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

# Get the root logger
logger = logging.getLogger()

# Configurar logging do Pika para WARNING
logging.getLogger("pika").setLevel(logging.WARNING)

# Adicionar handler para warnings do Pika em arquivo separado
pika_warning_handler = logging.FileHandler("rabbitmq_warnings.log", encoding="utf-8")
pika_warning_handler.setLevel(logging.WARNING)
pika_warning_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger("pika").addHandler(pika_warning_handler)

# Create directories
os.makedirs("temp", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
os.makedirs("document", exist_ok=True)

app = FastAPI(
    title="CNPJ Processing API",
    description="API for processing CNPJ data and interacting with external websites",
    version="1.0.0",
    # Add security scheme configuration for Bearer token
    openapi_tags=[
        {"name": "Authentication", "description": "Authentication operations"},
        {"name": "CNPJ Processing", "description": "CNPJ processing operations"},
        {"name": "Excel Upload", "description": "Excel file upload operations"}
    ],
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},  # Hide schemas section by default
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories if they don't exist
os.makedirs("document", exist_ok=True)

# Mount the document directory as a static files directory
app.mount("/document", StaticFiles(directory="document"), name="document")

# Create an API router to group all endpoints under /api
api_router = APIRouter(prefix="/api")

# Include all routers under the /api prefix
api_router.include_router(cnpj.router)
api_router.include_router(excel.router)
api_router.include_router(auth.router)  # Incluir roteador de autenticação

# Add the API router to the main app
app.include_router(api_router)

# Filter paths in OpenAPI schema
original_openapi = app.openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Get the default OpenAPI schema
    openapi_schema = original_openapi()
    
    # Add security scheme for Bearer token
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your bearer token in the format: **Bearer &lt;token&gt;**"
        }
    }
    
    # Define which paths and methods to include
    allowed_endpoints = {
        "/api/cnpj/process": ["POST"],
        "/api/cnpj/validate-excel": ["POST"], 
        "/api/cnpj/reprocess-pending": ["POST"],
        "/api/auth/token": ["POST"],
        "/api/auth/register": ["POST"],
        "/api/auth/register-first-user": ["POST"],
        "/api/cnpj/delete-batch": ["DELETE"],
        "/api/cnpj/{fila_id}": ["DELETE"]
    }
    
    # Filter paths
    filtered_paths = {}
    for path, path_item in openapi_schema["paths"].items():
        if path in allowed_endpoints:
            # Filter methods for this path
            filtered_path_item = {}
            for method, operation in path_item.items():
                # Convert method to uppercase for comparison
                if method.upper() in allowed_endpoints[path]:
                    # Add security requirement to protected endpoints
                    if path != "/api/auth/token" and path != "/api/auth/register-first-user":
                        operation["security"] = [{"Bearer": []}]
                    filtered_path_item[method] = operation
            
            if filtered_path_item:  # Only add if there are allowed methods
                filtered_paths[path] = filtered_path_item
    
    openapi_schema["paths"] = filtered_paths
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Override the openapi function
app.openapi = custom_openapi

# Cleanup function to kill any hanging chrome processes
def cleanup_chrome_processes():
    """
    Kill any hanging Chrome processes to prevent resource leaks
    """
    try:
        logger.info("Cleaning up Chrome processes...")
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_name = proc.info['name'].lower()
                if 'chrome' in proc_name or 'chromedriver' in proc_name:
                    # Try to check if our script is the parent or grandparent
                    is_child = False
                    process = psutil.Process(proc.info['pid'])
                    
                    # Check if it's orphaned or if we should terminate it
                    try:
                        parent = process.parent()
                        if parent and parent.pid == os.getpid():
                            is_child = True
                        # Also check for grandparent relationship (chromedriver -> chrome)
                        elif parent:
                            try:
                                grandparent = parent.parent()
                                if grandparent and grandparent.pid == os.getpid():
                                    is_child = True
                            except:
                                pass
                    except:
                        pass
                    
                    if is_child or 'chromedriver' in proc_name:
                        logger.info(f"Terminating Chrome process: {proc.info['pid']}")
                        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                            process.terminate()
                            
                        # Wait a short time for graceful termination
                        try:
                            process.wait(timeout=2)
                        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                            # Force kill if it didn't terminate gracefully
                            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                logger.error(f"Error cleaning up Chrome process: {str(e)}")
    except Exception as e:
        logger.error(f"Error in Chrome cleanup: {str(e)}")
        
    logger.info("Chrome process cleanup completed")

# Clean up on startup 
cleanup_chrome_processes()

# Register cleanup on shutdown
atexit.register(cleanup_chrome_processes)

# Register SIGTERM handler for containerized environments
def handle_sigterm(*args):
    """Handle SIGTERM signal for graceful shutdown in containerized environments"""
    logger.info("Received SIGTERM signal, cleaning up...")
    cleanup_chrome_processes()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

# Health check endpoint
@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok", "timestamp": time.time()}

# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Welcome to CNPJ Processing API",
        "docs": "/docs",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    try:
        # Try cleaning up any zombie Chrome processes first
        cleanup_chrome_processes()
        
        # Start the server
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    except KeyboardInterrupt:
        logger.info("Server shutdown initiated by user")
        cleanup_chrome_processes()
    except Exception as e:
        logger.error(f"Error running server: {str(e)}")
        cleanup_chrome_processes()
        sys.exit(1)
    finally:
        # Ensure cleanup happens
        cleanup_chrome_processes() 