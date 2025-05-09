import uvicorn
from fastapi import FastAPI, HTTPException
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
    version="1.0.0"
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

# Include routers
app.include_router(cnpj.router)

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
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": time.time()}

# Root endpoint
@app.get("/")
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