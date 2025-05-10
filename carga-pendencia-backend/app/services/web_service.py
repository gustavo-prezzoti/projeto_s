from typing import Dict, Any, Optional
import logging
import time
import os
import sys
import platform
import subprocess
from datetime import datetime
from pathlib import Path
import random
import json
import psutil  # Importando psutil para gerenciamento de processos
import glob
import shutil
import re
import traceback
from bs4 import BeautifulSoup

try:
    import pyautogui

    pyautogui_available = True
except ImportError:
    pyautogui_available = False

# Selenium imports
from seleniumwire import webdriver  # type: ignore
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


class WebService:
    """
    Service for interacting with external websites using Selenium
    """

    @staticmethod
    def wait_for_form_changes(driver, current_elements_count, timeout=15):
        """
        Espera até que o número de elementos do formulário mude, indicando que o DOM foi atualizado
        """
        logger.info(
            f"Esperando pela atualização do formulário. Contagem atual: {current_elements_count}"
        )
        start_time = time.time()
        while time.time() - start_time < timeout:
            new_count = len(driver.find_elements(By.TAG_NAME, "input"))
            if new_count != current_elements_count:
                logger.info(
                    f"Formulário atualizado! Nova contagem: {new_count}"
                )
                return True
            time.sleep(0.5)
        logger.warning(
            f"Timeout esperando mudanças no formulário após {timeout} segundos"
        )
        return False

    @staticmethod
    def wait_for_loading_overlay(driver, timeout=8):
        """
        Espera até que qualquer overlay de carregamento desapareça
        """
        logger.info("Verificando overlays de carregamento...")
        loading_overlay_xpath = '//div[contains(@class, "mostrar_carregando") or contains(@class, "loading")]'
        loading_elements = driver.find_elements(
            By.XPATH, loading_overlay_xpath
        )

        if not loading_elements:
            logger.info("Nenhum overlay de carregamento encontrado")
            return True

        logger.info(
            f"Encontrados {len(loading_elements)} possíveis elementos de carregamento, aguardando..."
        )
        try:
            WebDriverWait(driver, timeout).until_not(
                lambda d: any(
                    elem.is_displayed()
                    for elem in d.find_elements(
                        By.XPATH, loading_overlay_xpath
                    )
                    if elem
                )
            )
            logger.info("Overlay de carregamento desapareceu")
            return True
        except TimeoutException:
            logger.warning(
                f"Timeout esperando o desaparecimento do overlay após {timeout} segundos"
            )
            return False

    @staticmethod
    def wait_for_element_stable(driver, by, selector, timeout=5):
        """
        Espera até que um elemento esteja estável (não mude por um período)
        """
        logger.info(f"Aguardando elemento estável: {selector}")
        start_time = time.time()
        last_html = ""

        while time.time() - start_time < timeout:
            try:
                element = driver.find_element(by, selector)
                current_html = element.get_attribute("outerHTML")
                if current_html == last_html:
                    return element
                last_html = current_html
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            time.sleep(0.5)

        logger.warning(f"Elemento não estabilizou após {timeout} segundos")
        try:
            return driver.find_element(by, selector)
        except Exception as e:
            logger.error(
                f"Não foi possível encontrar o elemento após espera: {str(e)}"
            )
            return None

    @staticmethod
    async def navigate_to_gpi_portal(
        cnpj: str,
        headless: bool = False,
        fila_id: int = None,
        wait_times: dict = None,
    ) -> Dict[str, Any]:
        """
        Navigate to the GPI portal and perform the required clicks

        Args:
            cnpj: The CNPJ to process
            headless: Whether to run browser in headless mode (set to False to visualize)
            fila_id: ID da fila para nomear o PDF
            wait_times: Tempos de espera calculados dinamicamente

        Returns:
            Dictionary with results of the web interaction
        """
        logger.info(f"Starting web navigation for CNPJ: {cnpj}")
        screenshots = []

        # Definir tempos de espera padrão se não forem fornecidos
        if wait_times is None:
            wait_times = {
                "page_load": 40,  # Aumentado de 20 para 40
                "after_click": 20,  # Aumentado de 10 para 20
                "form_fill": 10,  # Aumentado de 5 para 10
                "element_wait": 30,  # Aumentado de 10 para 30
                "between_tasks": 5,  # Aumentado de 3 para 5
            }
        else:
            # Garantir valores mínimos para sistemas com conexão lenta
            wait_times["page_load"] = max(wait_times.get("page_load", 20), 30)
            wait_times["after_click"] = max(wait_times.get("after_click", 10), 15)
            wait_times["form_fill"] = max(wait_times.get("form_fill", 5), 8)
            wait_times["element_wait"] = max(wait_times.get("element_wait", 10), 20)
            wait_times["between_tasks"] = max(wait_times.get("between_tasks", 3), 5)

        logger.info(
            f"Usando tempos de espera: page_load={wait_times['page_load']}s, after_click={wait_times['after_click']}s"
        )

        # Inicializar actions_status para evitar UnboundLocalError
        actions_status = {
            "first_radio": "unknown",
            "cnpj_radio": "unknown",
            "cnpj_input": "unknown",
            "submit_button": "unknown",
        }

        # Inicializar variáveis de controle com default False
        radio_clicked = False
        cnpj_radio_clicked = False
        cnpj_entered = False
        button_clicked = False

        driver = None
        try:
            # Create screenshots directory if it doesn't exist
            screenshots_dir = Path("screenshots")
            screenshots_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Usar apenas o Chrome
            driver = None
            browser_used = ""
            try:
                chrome_options = ChromeOptions()
                if headless:
                    chrome_options.add_argument("--headless=chrome")
                    chrome_options.add_argument("--kiosk-printing")
                    chrome_options.add_argument("--disable-gpu")
                # Configurações comuns aos dois modos
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--window-size=1280,800")
                # Adicionar mais opções para melhorar compatibilidade
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-default-apps")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument(
                    "--disable-blink-features=AutomationControlled"
                )
                chrome_options.add_argument("--start-maximized")
                # Desabilitar impressão automática
                chrome_options.add_argument("--disable-print-preview")
                # Simular usuário real para evitar detecção de automação
                chrome_options.add_argument(
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                chrome_options.add_experimental_option(
                    "excludeSwitches", ["enable-automation"]
                )
                chrome_options.add_experimental_option(
                    "useAutomationExtension", False
                )
                # Configuração para baixar PDF automaticamente na pasta 'document'
                download_dir = os.path.abspath("document")
                os.makedirs(download_dir, exist_ok=True)
                prefs = {
                    "printing.print_preview_sticky_settings.appState": json.dumps(
                        {
                            "recentDestinations": [
                                {
                                    "id": "Save as PDF",
                                    "origin": "local",
                                    "account": "",
                                }
                            ],
                            "selectedDestinationId": "Save as PDF",
                            "version": 2,
                        }
                    ),
                    "savefile.default_directory": download_dir,
                    "download.default_directory": download_dir,
                    "download.prompt_for_download": False,
                    "download.directory_upgrade": True,
                    "plugins.always_open_pdf_externally": True,
                    "printing.default_destination_selection_rules": json.dumps(
                        {
                            "kind": "local",
                            "namePattern": "Save as PDF",
                        }
                    ),
                    "printing.print_preview_sticky_settings.mostRecentlyUsedDestinations": json.dumps(
                        [
                            {
                                "id": "Save as PDF",
                                "origin": "local",
                                "account": "",
                            }
                        ]
                    ),
                }
                chrome_options.add_experimental_option("prefs", prefs)

                # Lidar com problemas de conexão
                driver = webdriver.Chrome(options=chrome_options)

                browser_used = "Chrome"
                logger.info("Using Chrome browser")

                # Se não estiver em modo headless, tentar ocultar a janela do Chrome
                if not headless:
                    try:
                        # Esperar um pouco para o Chrome inicializar
                        time.sleep(5)

                        # Detectar sistema operacional
                        system = platform.system().lower()

                        if "win" in system:  # Windows
                            try:
                                # Tentar minimizar via win32gui se disponível (apenas Windows)
                                import win32gui
                                import win32con

                                def callback(hwnd, windows):
                                    text = win32gui.GetWindowText(hwnd)
                                    if (
                                        "chrome" in text.lower()
                                        and win32gui.IsWindowVisible(hwnd)
                                    ):
                                        windows.append(hwnd)
                                    return True

                                chrome_windows = []
                                win32gui.EnumWindows(callback, chrome_windows)

                                for hwnd in chrome_windows:
                                    win32gui.ShowWindow(
                                        hwnd, win32con.SW_MINIMIZE
                                    )
                                    logger.info(
                                        f"Janela do Chrome minimizada: {hwnd}"
                                    )
                            except ImportError:
                                logger.info(
                                    "Módulo win32gui não disponível para minimizar janela no Windows"
                                )

                        elif "linux" in system:  # Linux/Ubuntu
                            try:
                                # No Linux/Ubuntu, podemos tentar o XDOTOOL se disponível
                                import subprocess

                                # Verificar se o xdotool está instalado
                                try:
                                    subprocess.run(
                                        ["which", "xdotool"],
                                        check=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                    )

                                    # Usar xdotool para minimizar janelas do Chrome
                                    cmd = "xdotool search --class 'Chrome' windowminimize"
                                    subprocess.run(
                                        cmd, shell=True, stderr=subprocess.PIPE
                                    )
                                    logger.info(
                                        "Janelas do Chrome minimizadas via xdotool no Linux"
                                    )
                                except subprocess.CalledProcessError:
                                    logger.info(
                                        "xdotool não encontrado no sistema. Instale-o com: sudo apt-get install xdotool"
                                    )
                            except Exception as linux_error:
                                logger.warning(
                                    f"Não foi possível minimizar janelas no Linux: {str(linux_error)}"
                                )

                        else:  # macOS ou outro
                            logger.info(
                                f"Ocultação avançada de janelas não implementada para {system}"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Não foi possível ocultar completamente a janela do Chrome: {str(e)}"
                        )
            except Exception as chrome_error:
                raise Exception(
                    f"Failed to initialize Chrome browser: {str(chrome_error)}"
                )

            if not driver:
                raise Exception("Failed to initialize Chrome browser")

            try:
                # Configure browser window size
                driver.set_window_size(1280, 800)

                # Navigate to the GPI portal
                portal_url = "https://gpi18.cloud.el.com.br/ServerExec/acessoBase/?idPortal=008D9DCE8EF2707B45F47C2AD10B38E2&idFunc=ee6f9a8f-2a52-4e3f-af53-380ca41cf307"
                logger.info(f"Navegando para URL: {portal_url!r}")
                if not portal_url or not portal_url.startswith("http"):
                    logger.error(
                        f"URL inválida para navegação: {portal_url!r}"
                    )
                    raise ValueError(f"URL inválida: {portal_url!r}")
                driver.get(portal_url)

                # Adicionar um script que será executado em toda mudança de página
                # Este script desativa todas as formas conhecidas de abrir a impressão
                try:
                    logger.info(
                        "Injetando script para interceptar todas as tentativas de impressão"
                    )
                    script = """
                    // Substituir a função window.print
                    window.originalPrint = window.print;
                    window.print = function() { 
                        console.log('[Interceptado] Tentativa de abrir diálogo de impressão via window.print() bloqueada');
                        return false;
                    };
                    
                    // Substituir a função de abertura de nova janela
                    window.originalOpen = window.open;
                    window.open = function(url, name, specs) {
                        if (specs && specs.includes('print')) {
                            console.log('[Interceptado] Tentativa de abrir janela de impressão via window.open() bloqueada');
                            return null;
                        }
                        return window.originalOpen(url, name, specs);
                    };
                    
                    // Desativar atalhos de teclado para imprimir
                    document.addEventListener('keydown', function(e) {
                        if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
                            console.log('[Interceptado] Atalho de teclado para impressão bloqueado');
                            e.preventDefault();
                            return false;
                        }
                    }, true);
                    
                    // Interceptar gatilhos de impressão baseados em eventos
                    document.addEventListener('DOMContentLoaded', function() {
                        console.log('[Script] Interceptador de impressão instalado');
                    });
                    
                    console.log('[Script] Proteção contra impressão instalada');
                    """
                    driver.execute_script(script)
                    logger.info(
                        "Script de proteção contra impressão instalado com sucesso"
                    )
                except Exception as script_err:
                    logger.warning(
                        f"Erro ao instalar script de proteção contra impressão: {script_err}"
                    )

                # Desabilitar window.print() para evitar diálogo de impressão automático
                try:
                    logger.info(
                        "Tentando desabilitar window.print() para evitar diálogo de impressão automático"
                    )
                    driver.execute_script(
                        """
                        window.originalPrint = window.print;
                        window.print = function() { 
                            console.log('Função window.print() desabilitada');
                            return false;
                        };
                    """
                    )
                    logger.info(
                        "Função window.print() desabilitada com sucesso"
                    )
                except Exception as print_err:
                    logger.warning(
                        f"Não foi possível desabilitar window.print(): {print_err}"
                    )

                # Add a significant initial waiting period (20 seconds) before any interaction
                logger.info(
                    f"Waiting {wait_times['page_load']} seconds for the page to fully load before any interaction..."
                )
                time.sleep(
                    wait_times["page_load"]
                )  # Tempo dinâmico baseado no batch size

                # Wait for any loading overlays to disappear
                try:
                    # First, wait for the page to load, but with a more resilient approach
                    logger.info("Waiting for initial element to appear...")

                    # Try using a shorter timeout and handle the exception gracefully
                    first_element_present = False
                    try:
                        WebDriverWait(
                            driver, wait_times["element_wait"]
                        ).until(
                            EC.presence_of_element_located(
                                (By.XPATH, '//*[@id="gwt-uid-1"]/li/a')
                            )
                        )
                        first_element_present = True
                        logger.info("First element found with original XPath")
                    except TimeoutException:
                        logger.warning(
                            f"Timeout waiting for first element with original XPath after {wait_times['element_wait']}s, trying alternative approaches"
                        )

                        # Try alternative approaches to find elements
                        try:
                            # Look for any links on the page
                            links = driver.find_elements(By.TAG_NAME, "a")
                            if links:
                                logger.info(
                                    f"Found {len(links)} links on the page"
                                )
                                first_element_present = True

                            # Look for any clickable elements
                            buttons = driver.find_elements(
                                By.TAG_NAME, "button"
                            )
                            if buttons:
                                logger.info(
                                    f"Found {len(buttons)} buttons on the page"
                                )
                                first_element_present = True

                            # If we found any interactive elements, consider the page loaded
                            if first_element_present:
                                logger.info(
                                    "Found alternative interactive elements on the page"
                                )
                            else:
                                # If still nothing, check if there's any content at all
                                body_text = driver.find_element(
                                    By.TAG_NAME, "body"
                                ).text
                                if body_text and len(body_text) > 10:
                                    logger.info(
                                        f"Page has text content: {body_text[:100]}..."
                                    )
                                    first_element_present = True
                                else:
                                    logger.warning(
                                        "Page doesn't appear to have loaded any content"
                                    )
                        except Exception as alt_error:
                            logger.warning(
                                f"Error in alternative element search: {str(alt_error)}"
                            )

                    # Always let the page stabilize a bit more if needed
                    time.sleep(wait_times["after_click"])

                    # Then, wait for any loading overlays to disappear (if they exist)
                    spinner_xpath = '//div[contains(@class, "loading") or contains(@class, "spinner") or contains(@class, "wait") or contains(@class, "carregando")]'
                    WebService.wait_for_spinner_and_dom_stable(
                        driver,
                        spinner_xpath,
                        stable_time=wait_times["after_click"],
                        timeout=wait_times["page_load"],
                    )
                except Exception as wait_error:
                    logger.warning(
                        f"Wait error (continuing anyway): {str(wait_error)}"
                    )

                # Click on the first element with JavaScript to avoid intercepted click
                try:
                    first_element_xpath = '//*[@id="gwt-uid-1"]/li/a'
                    first_element_css = "#gwt-uid-1 > li > a"
                    first_element_clicked = False
                    # Try with the original XPath approach first
                    try:
                        logger.info(
                            "Attempting to click first element with original XPath"
                        )
                        try:
                            first_element = WebDriverWait(driver, 8).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, first_element_xpath)
                                )
                            )
                            first_element.click()
                            first_element_clicked = True
                            time.sleep(wait_times["after_click"])
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro elemento com XPath original"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except ElementClickInterceptedException:
                            logger.info(
                                "Using JavaScript click for first element (original XPath)"
                            )
                            element = driver.find_element(
                                By.XPATH, first_element_xpath
                            )
                            driver.execute_script(
                                "arguments[0].click();", element
                            )
                            first_element_clicked = True
                            time.sleep(wait_times["after_click"])
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro elemento com JavaScript click e XPath original"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except TimeoutException:
                            logger.warning(
                                "Timeout waiting for first element to be clickable with original XPath"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not click first element with original XPath: {str(e)}"
                        )
                    # Try CSS Selector if XPath failed
                    if not first_element_clicked:
                        try:
                            logger.info(
                                "Trying to click first element with CSS Selector"
                            )
                            first_element_css_elem = driver.find_element(
                                By.CSS_SELECTOR, first_element_css
                            )
                            driver.execute_script(
                                "arguments[0].click();", first_element_css_elem
                            )
                            first_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro elemento com CSS Selector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click first element with CSS Selector: {str(e)}"
                            )
                    # Try JS direct querySelector if still not clicked
                    if not first_element_clicked:
                        try:
                            logger.info(
                                "Trying to click first element with JS querySelector"
                            )
                            driver.execute_script(
                                'document.querySelector("#gwt-uid-1 > li > a").click();'
                            )
                            first_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro elemento com JS querySelector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click first element with JS querySelector: {str(e)}"
                            )
                    # Try full XPath if still not clicked
                    if not first_element_clicked:
                        try:
                            logger.info(
                                "Trying to click first element with full XPath"
                            )
                            full_xpath = "/html/body/div[4]/div[2]/div/div/div/div[2]/div/div/div/div/div/div/div/div/div/ul/li/a"
                            elem_full_xpath = driver.find_element(
                                By.XPATH, full_xpath
                            )
                            driver.execute_script(
                                "arguments[0].click();", elem_full_xpath
                            )
                            first_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro elemento com XPath completo"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click first element with full XPath: {str(e)}"
                            )
                    # If the original approach didn't work, try alternatives
                    if not first_element_clicked:
                        logger.info(
                            "Trying alternative approaches to click first interactive element"
                        )

                        # Try clicking the first link on the page
                        try:
                            links = driver.find_elements(By.TAG_NAME, "a")
                            if links:
                                logger.info(
                                    f"Found {len(links)} links, trying to click the first one"
                                )
                                driver.execute_script(
                                    "arguments[0].click();", links[0]
                                )
                                first_element_clicked = True
                                time.sleep(
                                    5
                                )  # Aguarda 5 segundos após clicar no primeiro link
                                logger.info(
                                    "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro link na página"
                                )
                                radio_clicked = True
                                actions_status["first_radio"] = "success"
                            else:
                                logger.warning("No links found to click")
                        except Exception as link_error:
                            logger.warning(
                                f"Error clicking first link: {str(link_error)}"
                            )

                        # If still no success, try the first button
                        if not first_element_clicked:
                            try:
                                buttons = driver.find_elements(
                                    By.TAG_NAME, "button"
                                )
                                if buttons:
                                    logger.info(
                                        f"Found {len(buttons)} buttons, trying to click the first one"
                                    )
                                    driver.execute_script(
                                        "arguments[0].click();", buttons[0]
                                    )
                                    first_element_clicked = True
                                    time.sleep(
                                        5
                                    )  # Aguarda 5 segundos após clicar no primeiro botão
                                    logger.info(
                                        "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro botão na página"
                                    )
                                    radio_clicked = True
                                    actions_status["first_radio"] = "success"
                                else:
                                    logger.warning("No buttons found to click")
                            except Exception as button_error:
                                logger.warning(
                                    f"Error clicking first button: {str(button_error)}"
                                )

                        # If still nothing worked, try clicking anything that looks interactive
                        if not first_element_clicked:
                            try:
                                logger.info(
                                    "Trying to find any interactive element"
                                )
                                # Try to find elements that are commonly interactive
                                interactive_elements = driver.find_elements(
                                    By.CSS_SELECTOR,
                                    "a, button, input[type='button'], input[type='submit'], .clickable, [role='button']",
                                )

                                if interactive_elements:
                                    logger.info(
                                        f"Found {len(interactive_elements)} potential interactive elements"
                                    )
                                    for i, elem in enumerate(
                                        interactive_elements[:5]
                                    ):  # Try the first 5 at most
                                        try:
                                            is_visible = elem.is_displayed()
                                            elem_text = (
                                                elem.text.strip()
                                                if elem.text
                                                else "[No text]"
                                            )
                                            logger.info(
                                                f"Element {i+1}: visible={is_visible}, text={elem_text}"
                                            )

                                            if is_visible:
                                                driver.execute_script(
                                                    "arguments[0].click();",
                                                    elem,
                                                )
                                                first_element_clicked = True
                                                time.sleep(
                                                    5
                                                )  # Aguarda 5 segundos após clicar no elemento interativo
                                                logger.info(
                                                    f"✅ ETAPA 1 CONCLUÍDA: Clicou no elemento interativo {i+1}"
                                                )
                                                radio_clicked = True
                                                actions_status[
                                                    "first_radio"
                                                ] = "success"
                                                break
                                        except Exception as elem_error:
                                            logger.warning(
                                                f"Error with interactive element {i+1}: {str(elem_error)}"
                                            )
                                    else:
                                        logger.warning(
                                            "No potential interactive elements found"
                                        )
                                else:
                                    logger.warning(
                                        "No potential interactive elements found"
                                    )
                            except Exception as interactive_error:
                                logger.warning(
                                    f"Error finding interactive elements: {str(interactive_error)}"
                                )

                    if first_element_clicked:
                        logger.info(
                            "Successfully clicked first element (either original or alternative)"
                        )
                    else:
                        logger.warning(
                            "Failed to click any first element, attempting to continue anyway"
                        )

                    # Wait for any loading overlays to disappear
                    try:
                        loading_overlay_xpath = '//div[contains(@class, "mostrar_carregando") or contains(@class, "loading")]'
                        loading_elements = driver.find_elements(
                            By.XPATH, loading_overlay_xpath
                        )
                        if loading_elements:
                            WebDriverWait(driver, 20).until(
                                EC.invisibility_of_element_located(
                                    (By.XPATH, loading_overlay_xpath)
                                )
                            )
                            logger.info(
                                "Loading overlay disappeared after first click"
                            )
                            time.sleep(
                                5
                            )  # Give an extra moment for the page to stabilize
                    except (TimeoutException, NoSuchElementException):
                        logger.info(
                            "No loading overlay found after first click"
                        )

                    # Wait for the second element to be clickable
                    second_element_xpath = (
                        '//*[@id="homePanel"]/div/div[2]/div[1]/div/div[5]'
                    )
                    second_element_css = "#homePanel > div > div:nth-child(2) > div:nth-child(1) > div > div:nth-child(5)"
                    second_element_clicked = False
                    # Try with the original XPath approach first
                    try:
                        logger.info(
                            "Attempting to click second element with original XPath"
                        )
                        try:
                            WebDriverWait(driver, 8).until(
                                EC.presence_of_element_located(
                                    (By.XPATH, second_element_xpath)
                                )
                            )
                            second_element = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, second_element_xpath)
                                )
                            )
                            second_element.click()
                            second_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no segundo elemento com XPath original"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except ElementClickInterceptedException:
                            logger.info(
                                "Using JavaScript click for second element"
                            )
                            second_element = driver.find_element(
                                By.XPATH, second_element_xpath
                            )
                            driver.execute_script(
                                "arguments[0].click();", second_element
                            )
                            second_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no segundo elemento com JavaScript click"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except TimeoutException:
                            logger.warning(
                                "Timeout waiting for second element to be clickable"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not click second element with original XPath: {str(e)}"
                        )
                    # Try CSS Selector if XPath failed
                    if not second_element_clicked:
                        try:
                            logger.info(
                                "Trying to click second element with CSS Selector"
                            )
                            second_element_css_elem = driver.find_element(
                                By.CSS_SELECTOR, second_element_css
                            )
                            driver.execute_script(
                                "arguments[0].click();",
                                second_element_css_elem,
                            )
                            second_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no segundo elemento com CSS Selector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click second element with CSS Selector: {str(e)}"
                            )
                    # Try JS direct querySelector if still not clicked
                    if not second_element_clicked:
                        try:
                            logger.info(
                                "Trying to click second element with JS querySelector"
                            )
                            driver.execute_script(
                                'document.querySelector("#homePanel > div > div:nth-child(2) > div:nth-child(1) > div > div:nth-child(5)").click();'
                            )
                            second_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no segundo elemento com JS querySelector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click second element with JS querySelector: {str(e)}"
                            )
                    # Try full XPath if still not clicked
                    if not second_element_clicked:
                        try:
                            logger.info(
                                "Trying to click second element with full XPath"
                            )
                            full_xpath = "/html/body/div[4]/div[2]/div/div/div/div[2]/div/div/div/div/div/div/div/div/div/div[1]/div[1]/div/div/div/div[2]/div[1]/div/div[5]"
                            elem_full_xpath = driver.find_element(
                                By.XPATH, full_xpath
                            )
                            driver.execute_script(
                                "arguments[0].click();", elem_full_xpath
                            )
                            second_element_clicked = True
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no segundo elemento com XPath completo"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click second element with full XPath: {str(e)}"
                            )
                    # If the original approach failed, try alternatives
                    if not second_element_clicked:
                        logger.info(
                            "Trying alternative approaches to find and click second element"
                        )

                        # First, try to find elements in the main panel
                        try:
                            # Look for elements that match a pattern of being a main menu item
                            panel_elements = driver.find_elements(
                                By.XPATH,
                                "//div[contains(@id, 'Panel')]//div[contains(@class, 'clickable') or contains(@class, 'menu') or contains(@class, 'item')]",
                            )

                            if panel_elements:
                                logger.info(
                                    f"Found {len(panel_elements)} potential panel elements"
                                )

                                # Try to click one that looks promising (e.g., 5th element if available)
                                if len(panel_elements) >= 5:
                                    target_index = (
                                        4  # 5th element (zero-indexed)
                                    )
                                else:
                                    target_index = (
                                        len(panel_elements) - 1
                                    )  # Last element

                                driver.execute_script(
                                    "arguments[0].scrollIntoView({block: 'center'});",
                                    panel_elements[target_index],
                                )
                                time.sleep(5)
                                driver.execute_script(
                                    "arguments[0].click();",
                                    panel_elements[target_index],
                                )
                                second_element_clicked = True
                                time.sleep(
                                    5
                                )  # Aguarda 5 segundos após clicar no elemento do painel
                                logger.info(
                                    f"✅ ETAPA 2 CONCLUÍDA: Clicou no elemento do painel no índice {target_index}"
                                )
                                radio_clicked = True
                                actions_status["first_radio"] = "success"
                            else:
                                logger.warning("No panel elements found")
                        except Exception as panel_error:
                            logger.warning(
                                f"Error finding/clicking panel elements: {str(panel_error)}"
                            )

                        # If still no success, try any visible div that might be clickable
                        if not second_element_clicked:
                            try:
                                divs = driver.find_elements(By.TAG_NAME, "div")
                                # Filter to only visible divs
                                visible_divs = [
                                    div
                                    for div in divs
                                    if div.is_displayed()
                                    and div.size["height"] > 10
                                    and div.size["width"] > 10
                                ]

                                if visible_divs:
                                    logger.info(
                                        f"Found {len(visible_divs)} visible divs, trying some that might be interactive"
                                    )

                                    # Try several divs that might be clickable (using a heuristic to pick ones that might be menu items)
                                    candidates = visible_divs[
                                        :10
                                    ]  # First 10 visible divs

                                    for i, div in enumerate(candidates):
                                        try:
                                            # Get info for logging
                                            div_text = (
                                                div.text.strip()
                                                if div.text
                                                else "[No text]"
                                            )
                                            div_class = (
                                                div.get_attribute("class")
                                                or "[No class]"
                                            )
                                            logger.info(
                                                f"Trying div {i+1}: text='{div_text}', class='{div_class}'"
                                            )

                                            # Try to click it
                                            driver.execute_script(
                                                "arguments[0].scrollIntoView({block: 'center'});",
                                                div,
                                            )
                                            time.sleep(0.5)
                                            driver.execute_script(
                                                "arguments[0].click();", div
                                            )
                                            second_element_clicked = True
                                            time.sleep(
                                                5
                                            )  # Aguarda 5 segundos após clicar no div
                                            logger.info(
                                                f"✅ ETAPA 2 CONCLUÍDA: Clicou no div no índice {i+1}"
                                            )
                                            radio_clicked = True
                                            actions_status["first_radio"] = (
                                                "success"
                                            )
                                            break
                                        except Exception as div_error:
                                            logger.warning(
                                                f"Error clicking div {i+1}: {str(div_error)}"
                                            )
                                    else:
                                        logger.warning("No visible divs found")
                            except Exception as div_error:
                                logger.warning(
                                    f"Error finding/clicking divs: {str(div_error)}"
                                )

                    if second_element_clicked:
                        logger.info(
                            "Successfully clicked second element (either original or alternative)"
                        )
                    else:
                        logger.warning(
                            "Failed to click any second element, attempting to continue anyway"
                        )

                    time.sleep(10)

                    logger.info(
                        "Looking for all input elements on the page..."
                    )

                    all_inputs = driver.find_elements(By.TAG_NAME, "input")
                    logger.info(f"Found {len(all_inputs)} input elements")

                    all_radios = driver.find_elements(
                        By.XPATH, "//input[@type='radio']"
                    )
                    logger.info(f"Found {len(all_radios)} radio buttons")

                    all_text_inputs = driver.find_elements(
                        By.XPATH, "//input[@type='text']"
                    )
                    logger.info(
                        f"Found {len(all_text_inputs)} text input fields"
                    )

                    radio_clicked = False

                    # Robust click for radio button
                    radio_xpath = '//*[@id="e9c5eec1-27d9-4cc0-81c0-befa3acb0f18"]/label/input'
                    radio_css = "#e9c5eec1-27d9-4cc0-81c0-befa3acb0f18 > label > input[type=radio]"
                    radio_clicked = False
                    try:
                        first_radio = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located(
                                (By.XPATH, radio_xpath)
                            )
                        )
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            first_radio,
                        )
                        time.sleep(5)
                        driver.execute_script(
                            "arguments[0].click();", first_radio
                        )
                        time.sleep(5)
                        logger.info(
                            "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro radio button com XPath original"
                        )
                        radio_clicked = True
                        actions_status["first_radio"] = "success"
                        logger.info(
                            "Waiting for form to update after first radio selection..."
                        )
                        initial_inputs_count = len(
                            driver.find_elements(By.TAG_NAME, "input")
                        )
                        WebService.wait_for_form_changes(
                            driver, initial_inputs_count
                        )
                        WebService.wait_for_loading_overlay(driver)
                    except TimeoutException:
                        logger.warning(
                            "Timeout waiting for radio button to appear"
                        )
                    # Try CSS Selector if XPath failed
                    if not radio_clicked:
                        try:
                            logger.info(
                                "Trying to click radio button with CSS Selector"
                            )
                            radio_css_elem = driver.find_element(
                                By.CSS_SELECTOR, radio_css
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                radio_css_elem,
                            )
                            time.sleep(5)
                            driver.execute_script(
                                "arguments[0].click();", radio_css_elem
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no radio button com CSS Selector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                            logger.info(
                                "Waiting for form to update after radio selection..."
                            )
                            initial_inputs_count = len(
                                driver.find_elements(By.TAG_NAME, "input")
                            )
                            WebService.wait_for_form_changes(
                                driver, initial_inputs_count
                            )
                            WebService.wait_for_loading_overlay(driver)
                        except Exception as e:
                            logger.warning(
                                f"Could not click radio with CSS Selector: {str(e)}"
                            )
                    # Try JS direct querySelector if still not clicked
                    if not radio_clicked:
                        try:
                            logger.info(
                                "Trying to click radio button with JS querySelector"
                            )
                            driver.execute_script(
                                'document.querySelector("#e9c5eec1-27d9-4cc0-81c0-befa3acb0f18 > label > input[type=radio]").click();'
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no radio button com JS querySelector"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                            logger.info(
                                "Waiting for form to update after radio selection..."
                            )
                            initial_inputs_count = len(
                                driver.find_elements(By.TAG_NAME, "input")
                            )
                            WebService.wait_for_form_changes(
                                driver, initial_inputs_count
                            )
                            WebService.wait_for_loading_overlay(driver)
                        except Exception as e:
                            logger.warning(
                                f"Could not click radio with JS querySelector: {str(e)}"
                            )
                    # Try full XPath if still not clicked
                    if not radio_clicked:
                        try:
                            logger.info(
                                "Trying to click radio button with full XPath"
                            )
                            full_xpath = "/html/body/div[4]/div[2]/div/div/div/div[2]/div/div/div/div/div/div/div/div/div/div[1]/div[3]/div/div/table/tbody/tr[3]/td/table/tbody/tr/td/form/div/div/table/tbody/tr/td/form/div/div/table/tbody/tr[2]/td/table/tbody/tr/td/form/div/div/table/tbody/tr/td[6]/div/label/input"
                            elem_full_xpath = driver.find_element(
                                By.XPATH, full_xpath
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                elem_full_xpath,
                            )
                            time.sleep(5)
                            driver.execute_script(
                                "arguments[0].click();", elem_full_xpath
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no radio button com XPath completo"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                            logger.info(
                                "Waiting for form to update after radio selection..."
                            )
                            initial_inputs_count = len(
                                driver.find_elements(By.TAG_NAME, "input")
                            )
                            WebService.wait_for_form_changes(
                                driver, initial_inputs_count
                            )
                            WebService.wait_for_loading_overlay(driver)
                        except Exception as e:
                            logger.warning(
                                f"Could not click radio with full XPath: {str(e)}"
                            )
                    # Fallback: Try by index if still not clicked
                    if not radio_clicked and all_radios:
                        try:
                            logger.info(
                                "Trying to click first radio button by index"
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                all_radios[0],
                            )
                            time.sleep(5)
                            driver.execute_script(
                                "arguments[0].click();", all_radios[0]
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 1 CONCLUÍDA: Clicou no primeiro radio button pelo índice"
                            )
                            radio_clicked = True
                            actions_status["first_radio"] = "success"
                            logger.info(
                                "Waiting for form to update after radio selection..."
                            )
                            initial_inputs_count = len(
                                driver.find_elements(By.TAG_NAME, "input")
                            )
                            WebService.wait_for_form_changes(
                                driver, initial_inputs_count
                            )
                            WebService.wait_for_loading_overlay(driver)
                        except Exception as e:
                            logger.warning(
                                f"Could not click first radio by index: {str(e)}"
                            )

                    try:
                        logger.info(
                            "Checking for loading overlays after first radio selection..."
                        )
                        loading_elements = driver.find_elements(
                            By.XPATH,
                            "//div[contains(@class, 'loading') or contains(@class, 'spinner') or contains(@class, 'wait')]",
                        )
                        if loading_elements:
                            logger.info(
                                f"Found {len(loading_elements)} possible loading elements, waiting for them to disappear"
                            )
                            WebService.wait_for_loading_overlay(
                                driver, timeout=10
                            )
                    except Exception as e:
                        logger.warning(
                            f"Error while waiting for loading elements: {str(e)}"
                        )

                    logger.info(
                        "Rechecking available form elements after first radio selection..."
                    )
                    all_inputs_after = driver.find_elements(
                        By.TAG_NAME, "input"
                    )
                    all_radios_after = driver.find_elements(
                        By.XPATH, "//input[@type='radio']"
                    )
                    all_text_inputs_after = driver.find_elements(
                        By.XPATH, "//input[@type='text']"
                    )

                    if len(all_inputs_after) != len(all_inputs) or len(
                        all_text_inputs_after
                    ) != len(all_text_inputs):
                        logger.info(
                            f"Form elements changed: before={len(all_inputs)}/{len(all_text_inputs)}, after={len(all_inputs_after)}/{len(all_text_inputs_after)}"
                        )
                        all_inputs = all_inputs_after
                        all_radios = all_radios_after
                        all_text_inputs = all_text_inputs_after
                    cnpj_radio_clicked = False
                    try:
                        cnpj_radio_xpath = '//*[@id="CNPJ"]/label/input'
                        cnpj_radio_clicked = (
                            WebService.click_element_resiliente(
                                driver, By.XPATH, cnpj_radio_xpath
                            )
                        )
                        if cnpj_radio_clicked:
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no radio button de CNPJ com XPath original"
                            )
                            actions_status["cnpj_radio"] = "success"
                    except Exception as e:
                        logger.warning(
                            f"Could not click CNPJ radio with original XPath: {str(e)}"
                        )
                    if not cnpj_radio_clicked and len(all_radios) > 1:
                        try:
                            logger.info(
                                "Trying to click CNPJ radio button by index"
                            )
                            driver.execute_script(
                                "arguments[0].click();", all_radios[1]
                            )
                            time.sleep(
                                5
                            )  # Aguarda 5 segundos após clicar no radio de CNPJ
                            logger.info(
                                "✅ ETAPA 2 CONCLUÍDA: Clicou no radio button de CNPJ pelo índice"
                            )
                            cnpj_radio_clicked = True
                            actions_status["cnpj_radio"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click CNPJ radio by index: {str(e)}"
                            )
                    if not cnpj_radio_clicked:
                        try:
                            logger.info(
                                "Trying to find CNPJ radio by label text"
                            )
                            labels = driver.find_elements(
                                By.XPATH, "//label[contains(text(), 'CNPJ')]"
                            )
                            if labels:
                                logger.info(
                                    f"Found {len(labels)} labels containing 'CNPJ'"
                                )
                                for label in labels:
                                    try:
                                        inputs = label.find_elements(
                                            By.XPATH, ".//input[@type='radio']"
                                        )
                                        if inputs:
                                            driver.execute_script(
                                                "arguments[0].click();",
                                                inputs[0],
                                            )
                                            time.sleep(
                                                5
                                            )  # Aguarda 5 segundos após clicar no radio de CNPJ
                                            logger.info(
                                                "✅ ETAPA 2 CONCLUÍDA: Clicou no radio button de CNPJ encontrando-o em uma label"
                                            )
                                            cnpj_radio_clicked = True
                                            actions_status["cnpj_radio"] = (
                                                "success"
                                            )
                                            break
                                    except Exception as e:
                                        logger.warning(
                                            f"Error with label: {str(e)}"
                                        )
                        except Exception as e:
                            logger.warning(
                                f"Could not find CNPJ radio by label: {str(e)}"
                            )
                    cnpj_entered = False
                    cnpj_xpath = '//*[@id="DataEntryForm_dataForm__6"]/div/div/table/tbody/tr[6]/td/table/tbody/tr/td/table/tbody/tr[2]/td/input'
                    cnpj_css = "#DataEntryForm_dataForm__6 > div > div > table > tbody > tr:nth-child(6) > td > table > tbody > tr > td > table > tbody > tr:nth-child(2) > td > input"
                    try:
                        logger.info(
                            f"Tentando preencher CNPJ {cnpj} com abordagem de espera explícita..."
                        )
                        WebDriverWait(
                            driver, wait_times["element_wait"]
                        ).until(
                            EC.presence_of_element_located(
                                (By.XPATH, cnpj_xpath)
                            )
                        )
                        cnpj_input = driver.find_element(By.XPATH, cnpj_xpath)
                        driver.execute_script(
                            "arguments[0].focus();", cnpj_input
                        )
                        cnpj_input.clear()
                        for char in cnpj:
                            cnpj_input.send_keys(char)
                            time.sleep(
                                wait_times["form_fill"] / 100
                            )  # Dividir o tempo total pelo número típico de caracteres
                        # Disparar apenas eventos no input, sem clicar fora
                        driver.execute_script(
                            """
                            var input = arguments[0];
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.dispatchEvent(new Event('blur', { bubbles: true }));
                        """,
                            cnpj_input,
                        )
                        logger.info(
                            f"✅ ETAPA 3 CONCLUÍDA: Preencheu CNPJ {cnpj} com abordagem robusta e sem mudar o foco"
                        )
                        cnpj_entered = True
                        actions_status["cnpj_input"] = "success"
                        # Após preencher o CNPJ, clicar diretamente no botão
                        button_xpath = '//*[@id="WorkPanel__4"]/tbody/tr[2]/td/div/div/div/div/table/tbody/tr/td[1]/button'
                        try:
                            button_elem = WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, button_xpath)
                                )
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                button_elem,
                            )
                            driver.execute_script(
                                "arguments[0].click();", button_elem
                            )
                            logger.info(
                                "✅ ETAPA 4 CONCLUÍDA: Clicou no botão após preencher o CNPJ"
                            )
                            button_clicked = True
                            actions_status["submit_button"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Falha ao clicar no botão após preencher o CNPJ: {str(e)}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Falha na abordagem principal para preenchimento do CNPJ: {str(e)}"
                        )
                    button_clicked = False
                    button_xpath = '//*[@id="WorkPanel__4"]/tbody/tr[2]/td/div/div/div/div/table/tbody/tr/td[1]/button'
                    button_css = "#WorkPanel__4 > tbody > tr:nth-child(2) > td > div > div > div > div > table > tbody > tr > td:nth-child(1) > button"
                    # Try with the original XPath approach first
                    try:
                        button_elem = driver.find_element(
                            By.XPATH, button_xpath
                        )
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            button_elem,
                        )
                        time.sleep(5)
                        driver.execute_script(
                            "arguments[0].click();", button_elem
                        )
                        time.sleep(5)
                        logger.info(
                            "✅ ETAPA 4 CONCLUÍDA: Clicou no botão com XPath original"
                        )
                        button_clicked = True
                        actions_status["submit_button"] = "success"
                    except Exception as e:
                        logger.warning(
                            f"Could not click button with original XPath: {str(e)}"
                        )
                    # Try CSS Selector if XPath failed
                    if not button_clicked:
                        try:
                            logger.info(
                                "Trying to click button with CSS Selector"
                            )
                            button_elem_css = driver.find_element(
                                By.CSS_SELECTOR, button_css
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                button_elem_css,
                            )
                            time.sleep(5)
                            driver.execute_script(
                                "arguments[0].click();", button_elem_css
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 4 CONCLUÍDA: Clicou no botão com CSS Selector"
                            )
                            button_clicked = True
                            actions_status["submit_button"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click button with CSS Selector: {str(e)}"
                            )
                    # Try JS direct querySelector if still not clicked
                    if not button_clicked:
                        try:
                            logger.info(
                                "Trying to click button with JS querySelector"
                            )
                            driver.execute_script(
                                'document.querySelector("#WorkPanel__4 > tbody > tr:nth-child(2) > td > div > div > div > div > table > tbody > tr > td:nth-child(1) > button").click();'
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 4 CONCLUÍDA: Clicou no botão com JS querySelector"
                            )
                            button_clicked = True
                            actions_status["submit_button"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click button with JS querySelector: {str(e)}"
                            )
                    # Try full XPath if still not clicked
                    if not button_clicked:
                        try:
                            logger.info(
                                "Trying to click button with full XPath"
                            )
                            full_xpath = "/html/body/div[4]/div[2]/div/div/div/div[2]/div/div/div/div/div/div/div/div/div/div[1]/div[3]/div/div/table/tbody/tr[2]/td/div/div/div/div/table/tbody/tr/td[1]/button"
                            button_elem_full = driver.find_element(
                                By.XPATH, full_xpath
                            )
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});",
                                button_elem_full,
                            )
                            time.sleep(5)
                            driver.execute_script(
                                "arguments[0].click();", button_elem_full
                            )
                            time.sleep(5)
                            logger.info(
                                "✅ ETAPA 4 CONCLUÍDA: Clicou no botão com XPath completo"
                            )
                            button_clicked = True
                            actions_status["submit_button"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click button with full XPath: {str(e)}"
                            )
                    # Fallback: Try click_element_resiliente if still not clicked
                    if not button_clicked:
                        try:
                            logger.info(
                                "Trying to click button with click_element_resiliente"
                            )
                            button_clicked = (
                                WebService.click_element_resiliente(
                                    driver, By.XPATH, button_xpath
                                )
                            )
                            if button_clicked:
                                logger.info(
                                    "✅ ETAPA 4 CONCLUÍDA: Clicou no botão usando função resiliente"
                                )
                                actions_status["submit_button"] = "success"
                        except Exception as e:
                            logger.warning(
                                f"Could not click button with click_element_resiliente: {str(e)}"
                            )

                    # Após clicar no botão, desabilitar novamente window.print()
                    try:
                        logger.info(
                            "Reforçando desativação do window.print() após clicar no botão"
                        )
                        driver.execute_script(
                            """
                            window.originalPrint = window.print;
                            window.print = function() { 
                                console.log('Função window.print() desabilitada após clique em botão');
                                return false;
                            };
                        """
                        )
                    except Exception as print_err:
                        logger.warning(
                            f"Falha ao desabilitar window.print() após botão: {print_err}"
                        )

                    # Verificar se uma nova aba foi aberta após clicar no botão
                    try:
                        logger.info(
                            "Verificando se uma nova aba foi aberta..."
                        )
                        # Aguarda um tempo para a nova aba ser aberta
                        time.sleep(5)

                        # Obtém todas as abas abertas
                        abas = driver.window_handles
                        logger.info(f"Número de abas abertas: {len(abas)}")

                        # Se tiver mais de uma aba, muda para a nova
                        if len(abas) > 1:
                            logger.info(
                                "Nova aba detectada! Mudando para a nova aba..."
                            )
                            # Muda para a última aba aberta
                            driver.switch_to.window(abas[-1])
                            logger.info("Mudou para a nova aba")

                            # Aguarda um pouco para a página carregar completamente
                            time.sleep(5)

                            # Tenta rolar a página para garantir que vemos todo o conteúdo
                            try:
                                # Rolar para o topo primeiro
                                driver.execute_script("window.scrollTo(0, 0);")
                                time.sleep(1)

                                # Rolar para o meio
                                driver.execute_script(
                                    "window.scrollTo(0, document.body.scrollHeight/2);"
                                )
                                time.sleep(1)

                                # Rolar para o fim
                                driver.execute_script(
                                    "window.scrollTo(0, document.body.scrollHeight);"
                                )
                                time.sleep(1)

                            except Exception as scroll_err:
                                logger.warning(
                                    f"Erro ao rolar a página: {scroll_err}"
                                )

                            # Tento capturar o título da página para debugging
                            try:
                                titulo = driver.title
                                logger.info(f"Título da nova aba: {titulo}")
                                url = driver.current_url
                                logger.info(f"URL da nova aba: {url}")
                            except Exception as title_err:
                                logger.warning(
                                    f"Erro ao obter título da página: {title_err}"
                                )

                            # Salvar HTML da nova aba
                            try:
                                html_path = f"screenshots/{timestamp}_new_tab_html.html"

                                # Usar JavaScript para obter o HTML completo com todos os recursos e estilos
                                try:
                                    # Primeiro tentar obter o documento HTML completo usando outerHTML
                                    new_tab_source = driver.execute_script(
                                        """
                                        // Função para extrair o HTML completo incluindo estilos computados inline
                                        return new XMLSerializer().serializeToString(document);
                                    """
                                    )
                                except Exception as js_err:
                                    logger.warning(
                                        f"Erro ao usar XMLSerializer: {js_err}. Usando método alternativo."
                                    )
                                    # Se falhar, usar page_source como fallback
                                    new_tab_source = driver.page_source

                                # Processar o HTML para garantir que todas as imagens e recursos serão renderizados corretamente no PDF
                                try:
                                    from bs4 import BeautifulSoup
                                    import requests
                                    import base64
                                    import re
                                    from urllib.parse import urljoin

                                    # Obter a URL base para recursos relativos
                                    base_url = driver.current_url
                                    domain = re.match(
                                        r"(https?://[^/]+)", base_url
                                    ).group(1)
                                    logger.info(
                                        f"URL base para recursos: {domain}"
                                    )

                                    soup = BeautifulSoup(
                                        new_tab_source, "html.parser"
                                    )

                                    # Remover script de impressão automática
                                    for script in soup.find_all("script"):
                                        if (
                                            script.string
                                            and "imprimir()" in script.string
                                        ):
                                            logger.info(
                                                "Removendo script de impressão automática"
                                            )
                                            script.decompose()

                                    # Extrair o texto completo para análise e armazenamento
                                    texto_completo = soup.get_text(
                                        separator="\n", strip=True
                                    )
                                    logger.info(
                                        f"Texto completo extraído: {texto_completo[:200]}..."
                                    )

                                    # Extrair especificamente o texto da div "texto" se existir
                                    texto_div = soup.select_one("div.texto")
                                    if texto_div:
                                        texto_certidao = texto_div.get_text(
                                            separator="\n", strip=True
                                        )
                                        logger.info(
                                            f"Texto extraído da div.texto: {texto_certidao[:200]}..."
                                        )
                                        texto_para_analise = texto_certidao
                                    else:
                                        texto_para_analise = texto_completo

                                    # Salvar o HTML completo para o full_result
                                    full_result = str(soup)
                                    logger.info(
                                        f"HTML processado com sucesso para armazenamento em full_result ({len(full_result)} caracteres)"
                                    )
                                    if not full_result.strip():
                                        logger.warning("full_result ficou vazio após processamento do soup! Usando new_tab_source como fallback.")
                                        full_result = new_tab_source
                                    logger.info(f"Tamanho final de full_result: {len(full_result)}")
                                except Exception as bs_err:
                                    logger.warning(
                                        f"Erro ao processar HTML para extração de texto: {bs_err}, usando HTML original"
                                    )
                                    full_result = new_tab_source
                                    logger.info(f"Tamanho de new_tab_source: {len(new_tab_source)}")

                                with open(
                                    html_path, "w", encoding="utf-8"
                                ) as f:
                                    f.write(full_result)
                                logger.info(
                                    f"HTML da nova aba salvo em {html_path}"
                                )

                                # Análise automática do status da dívida usando regex robusto
                                status_divida = "Status desconhecido"
                                if texto_para_analise:
                                    # Padrões mais abrangentes para detectar texto sobre pendências
                                    padrao_nao_constam = re.compile(
                                        r"n[ãa]o\s*(constam|há|ha|existem)\s*(pend[êe]ncias|d[íi]vidas|d[ée]bitos)?|(certificado\s+negativo)",
                                        re.IGNORECASE,
                                    )
                                    padrao_constam = re.compile(
                                        r"(constam|h[áa]|existem)\s*(pend[êe]ncias|d[íi]vidas|d[ée]bitos)|que\s+constam\s+d[íi]vidas",
                                        re.IGNORECASE,
                                    )
                                    # Primeiro vamos verificar se tem a palavra "não" junto com "constam"
                                    if padrao_nao_constam.search(
                                        texto_para_analise
                                    ):
                                        status_divida = (
                                            "Não constam pendências"
                                        )
                                    # Se não tem "não constam" mas tem "constam", então constam dívidas
                                    elif padrao_constam.search(
                                        texto_para_analise
                                    ):
                                        status_divida = "Constam dívidas"
                                    # Log do resultado da análise
                                    logger.info(
                                        f"Análise do texto: '{status_divida}' para texto: {texto_para_analise[:100]}..."
                                    )

                                # Limpar arquivos temporários
                                try:
                                    for screenshot in screenshots:
                                        if (
                                            os.path.exists(screenshot)
                                            and screenshot != html_path
                                        ):
                                            os.remove(screenshot)
                                            logger.info(
                                                f"Arquivo temporário removido: {screenshot}"
                                            )
                                except Exception as clean_err:
                                    logger.warning(
                                        f"Erro ao limpar arquivos temporários: {clean_err}"
                                    )

                                # Fechar o navegador
                                try:
                                    driver.quit()
                                except Exception as close_err:
                                    logger.warning(
                                        f"Erro ao fechar o navegador: {close_err}"
                                    )

                                # Retornar resultado
                                return {
                                    "status": "success",
                                    "message": "Texto extraído com sucesso",
                                    "resultado": (
                                        status_divida
                                        if status_divida
                                        != "Status desconhecido"
                                        else (
                                            texto_para_analise[:500]
                                            if texto_para_analise
                                            else ""
                                        )
                                    ),
                                    "texto_completo": (
                                        texto_completo
                                        if "texto_completo" in locals()
                                        else ""
                                    ),
                                    "status_divida": status_divida,
                                    "screenshots": screenshots,
                                    "full_result": (
                                        full_result
                                        if "full_result" in locals()
                                        else new_tab_source
                                    ),
                                }
                            except Exception as e:
                                print(
                                    f">>> Erro ao processar HTML e gerar PDF: {e}"
                                )
                                logger.error(
                                    f"Erro ao processar HTML e gerar PDF: {e}"
                                )
                                logger.error(traceback.format_exc())
                    except Exception as tab_err:
                        logger.warning(
                            f"Erro ao tentar verificar novas abas: {tab_err}"
                        )

                    # Em vez de imprimir, vamos extrair o texto solicitado
                    if button_clicked:
                        try:
                            logger.info(
                                "Tentando extrair o texto do elemento solicitado..."
                            )
                            # Aguarde um tempo maior para a página carregar completamente após o clique
                            logger.info(
                                "Aguardando 20 segundos para a página carregar completamente..."
                            )
                            time.sleep(20)

                            # MÉTODO DIRETO E ROBUSTO: Tentar pegar o texto específico da div.texto
                            # que sabemos estar presente na nova aba
                            logger.info(
                                "MÉTODO DIRETO: Tentando extrair texto da div.texto"
                            )
                            try:
                                texto_div = driver.find_element(
                                    By.CSS_SELECTOR, ".texto"
                                )
                                texto_certidao_direto = texto_div.text
                                if (
                                    texto_certidao_direto
                                    and len(texto_certidao_direto) > 20
                                ):
                                    logger.info(
                                        f"SUCESSO! Texto extraído diretamente da div.texto: {texto_certidao_direto[:200]}..."
                                    )
                                    # Inicializar variáveis importantes
                                    texto_completo = texto_certidao_direto
                                    textos_relevantes = [texto_certidao_direto]
                                    texto_para_analise = texto_certidao_direto
                                else:
                                    logger.warning(
                                        "Texto extraído da div.texto é muito curto ou vazio"
                                    )
                            except Exception as div_error:
                                logger.warning(
                                    f"Não foi possível extrair texto diretamente da div.texto: {div_error}"
                                )

                            # MÉTODO ALTERNATIVO: Extrair texto de elementos específicos
                            if (
                                "texto_para_analise" not in locals()
                                or not texto_para_analise
                            ):
                                logger.info(
                                    "MÉTODO ALTERNATIVO: Extraindo texto de elementos específicos"
                                )
                                try:
                                    texto_completo = driver.find_element(
                                        By.TAG_NAME, "body"
                                    ).text
                                    logger.info(
                                        f"Texto completo da página: {texto_completo[:200]}..."
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Erro ao extrair texto da página: {e}"
                                    )
                                    texto_completo = ""
                                if "textos_relevantes" not in locals():
                                    textos_relevantes = []
                                try:
                                    logger.info(
                                        "Tentando método JavaScript genérico..."
                                    )
                                    js_texto = driver.execute_script(
                                        """
                                        function getAllTextNodes(root) {
                                            var textNodes = [];
                                            var walk = document.createTreeWalker(
                                                root, 
                                                NodeFilter.SHOW_TEXT, 
                                                null, 
                                                false
                                            );
                                            while (walk.nextNode()) {
                                                if (walk.currentNode.nodeValue.trim()) {
                                                    textNodes.push(walk.currentNode.nodeValue.trim());
                                                }
                                            }
                                            return textNodes;
                                        }
                                        var allTexts = getAllTextNodes(document.body);
                                        var keywords = ['certificado', 'constam', 'pendências', 'dívidas', 'validade'];
                                        var relevantTexts = allTexts.filter(function(text) {
                                            var lowerText = text.toLowerCase();
                                            return keywords.some(function(kw) { return lowerText.indexOf(kw) >= 0; });
                                        });
                                        return relevantTexts.join('\\n');
                                    """
                                    )
                                    if js_texto and len(js_texto) > 20:
                                        logger.info(
                                            f"Texto extraído via JavaScript genérico: {js_texto[:200]}..."
                                        )
                                        textos_relevantes.append(js_texto)
                                except Exception as js_error:
                                    logger.warning(
                                        f"Erro no método JavaScript genérico: {js_error}"
                                    )
                                try:
                                    logger.info(
                                        "Tentando método JavaScript específico para certidão..."
                                    )
                                    certidao_especifica = driver.execute_script(
                                        """
                                        var textoDiv = document.querySelector('.texto');
                                        if (textoDiv) {
                                            return textoDiv.innerText || textoDiv.textContent;
                                        }
                                        var interface = document.querySelector('#interface');
                                        if (interface) {
                                            var textoDivs = interface.querySelectorAll('.texto');
                                            if (textoDivs && textoDivs.length > 0) {
                                                return textoDivs[0].innerText || textoDivs[0].textContent;
                                            }
                                        }
                                        var allP = document.querySelectorAll('p');
                                        for (var i = 0; i < allP.length; i++) {
                                            var text = allP[i].innerText || allP[i].textContent;
                                            if (text && text.toLowerCase().includes('constam')) {
                                                return text;
                                            }
                                        }
                                        return "";
                                    """
                                    )
                                    if (
                                        certidao_especifica
                                        and len(certidao_especifica) > 20
                                    ):
                                        logger.info(
                                            f"Texto específico da certidão encontrado via JS: {certidao_especifica[:200]}..."
                                        )
                                        textos_relevantes.append(
                                            certidao_especifica
                                        )
                                except Exception as js_cert_error:
                                    logger.warning(
                                        f"Erro no método JavaScript específico: {js_cert_error}"
                                    )
                                logger.info(
                                    "Procurando por elementos que podem conter texto relevante..."
                                )
                                # ... (continua o restante do código)
                        except Exception as e:
                            logger.error(
                                f"Erro ao tentar extrair texto da certidão: {e}"
                            )
                except (
                    Exception
                ) as click_button_error:  # Renomeei para evitar conflito de nomes
                    logger.error(f"Erro global: {click_button_error}")
                    logger.error(traceback.format_exc())

                    # Final status
                    actions_status = {
                        "first_radio": (
                            "success" if radio_clicked else "failed"
                        ),
                        "cnpj_radio": (
                            "success" if cnpj_radio_clicked else "failed"
                        ),
                        "cnpj_input": "success" if cnpj_entered else "failed",
                        "submit_button": (
                            "success" if button_clicked else "failed"
                        ),
                    }

                    logger.info(f"Actions status: {actions_status}")

                    # Se já extraiu o texto, retorne como sucesso
                    texto_final = None
                    if (
                        "status_divida" in locals()
                        and status_divida
                        and status_divida != "Status desconhecido"
                    ):
                        texto_final = status_divida
                    elif "texto_completo" in locals() and texto_completo:
                        texto_final = texto_completo
                    if texto_final:
                        try:
                            driver.quit()
                        except Exception as close_err:
                            logger.warning(
                                f"Erro ao fechar o navegador: {close_err}"
                            )
                        return {
                            "status": "success",
                            "message": "Texto extraído com sucesso (mesmo com erro Selenium)",
                            "resultado": texto_final,
                            "texto_completo": (
                                texto_completo
                                if "texto_completo" in locals()
                                else ""
                            ),
                            "status_divida": status_divida,
                            "screenshots": screenshots,
                            "full_result": (
                                full_result
                                if "full_result" in locals()
                                else new_tab_source
                            ),
                        }
                    return {
                        "status": "error",
                        "message": f"Error in web navigation: {str(e)}",
                        "url": "https://gpi18.cloud.el.com.br/ServerExec/acessoBase/?idPortal=008D9DCE8EF2707B45F47C2AD10B38E2&idFunc=ee6f9a8f-2a52-4e3f-af53-380ca41cf307",
                        "screenshots": screenshots,
                        "error": str(e),
                    }
            except Exception as e:
                logger.error(
                    f"Error during direct element interaction: {str(e)}"
                )
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {e.args}")

        except Exception as e:
            logger.error(f"Error in web navigation: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {e.args}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            # Se já extraiu o texto, retorne como sucesso
            texto_final = None
            if (
                "status_divida" in locals()
                and status_divida
                and status_divida != "Status desconhecido"
            ):
                texto_final = status_divida
            elif "texto_completo" in locals() and texto_completo:
                texto_final = texto_completo
            if texto_final:
                try:
                    driver.quit()
                except Exception as close_err:
                    logger.warning(f"Erro ao fechar o navegador: {close_err}")
                return {
                    "status": "success",
                    "message": "Texto extraído com sucesso (mesmo com erro Selenium)",
                    "resultado": texto_final,
                    "texto_completo": (
                        texto_completo if "texto_completo" in locals() else ""
                    ),
                    "status_divida": (
                        status_divida if "status_divida" in locals() else ""
                    ),
                    "screenshots": screenshots,
                }
            return {
                "status": "error",
                "message": f"Error in web navigation: {str(e)}",
                "url": "https://gpi18.cloud.el.com.br/ServerExec/acessoBase/?idPortal=008D9DCE8EF2707B45F47C2AD10B38E2&idFunc=ee6f9a8f-2a52-4e3f-af53-380ca41cf307",
                "screenshots": screenshots,
                "error": str(e),
            }

    @staticmethod
    def kill_chrome_processes(pid=None):
        """
        Kill Chrome processes to ensure resources are released.
        If pid is provided, only kill Chrome processes that are children of that pid.
        """
        try:
            system = platform.system().lower()

            # Se o PID específico foi fornecido, tenta matar apenas os processos filhos desse PID
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        if "chrome" in child.name().lower():
                            logger.info(
                                f"Matando processo Chrome filho (PID: {child.pid}) do processo {pid}"
                            )
                            child.terminate()
                    # Esperar processos terminarem
                    gone, still_alive = psutil.wait_procs(children, timeout=3)
                    # Forçar kill em processos que ainda estão vivos
                    for p in still_alive:
                        if "chrome" in p.name().lower():
                            logger.warning(
                                f"Forçando kill no processo Chrome {p.pid} que não terminou normalmente"
                            )
                            p.kill()
                except psutil.NoSuchProcess:
                    logger.info(
                        f"Processo pai {pid} não encontrado (já finalizado)."
                    )
                except Exception as e:
                    logger.error(
                        f"Erro ao matar processos Chrome filhos de {pid}: {str(e)}"
                    )

            # Abordagem específica para cada sistema operacional
            if "win" in system:  # Windows
                try:
                    # Listar e matar processos Chrome zumbis ou órfãos
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            # Se for Chrome ou ChromeDriver
                            if any(
                                chrome_name in proc.info["name"].lower()
                                for chrome_name in [
                                    "chrome.exe",
                                    "chromedriver.exe",
                                ]
                            ):
                                # Verificar se o processo está "pendurado" (sem resposta)
                                process = psutil.Process(proc.info["pid"])
                                if not process.is_running() or (
                                    hasattr(process, "status")
                                    and process.status()
                                    == psutil.STATUS_ZOMBIE
                                ):
                                    logger.warning(
                                        f"Encontrado processo Chrome zumbi ou pendurado: {proc.info['pid']}. Terminando..."
                                    )
                                    process.terminate()
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            continue
                except Exception as e:
                    logger.error(
                        f"Erro ao matar processos Chrome no Windows: {str(e)}"
                    )

            elif "linux" in system:  # Linux
                try:
                    # No Linux podemos usar comandos específicos
                    subprocess.run(
                        ["pkill", "-f", "chrome"], stderr=subprocess.PIPE
                    )
                    subprocess.run(
                        ["pkill", "-f", "chromedriver"], stderr=subprocess.PIPE
                    )
                except Exception as e:
                    logger.error(
                        f"Erro ao matar processos Chrome no Linux: {str(e)}"
                    )

            logger.info("Processo de limpeza de instâncias Chrome concluído")

        except Exception as e:
            logger.error(f"Erro ao tentar limpar processos Chrome: {str(e)}")

    @staticmethod
    def click_element_resiliente(
        driver, by, selector, tentativas=10, espera=10, total_timeout=60
    ):
        start = time.time()
        for tentativa in range(1, tentativas + 1):
            try:
                element = WebDriverWait(driver, espera).until(
                    EC.element_to_be_clickable((by, selector))
                )
                element.click()
                logger.info(
                    f"Clique bem-sucedido no elemento {selector} na tentativa {tentativa}"
                )
                return True
            except Exception as e:
                if time.time() - start > total_timeout:
                    logger.warning(
                        f"Timeout total ao tentar clicar no elemento {selector}: {e}"
                    )
                    return False
                logger.warning(
                    f"Tentativa {tentativa} falhou ao clicar no elemento {selector}: {e}"
                )
                time.sleep(5)
        return False

    @staticmethod
    def aguardar_pdf(download_dir, nome_esperado, timeout=60):
        start = time.time()
        while time.time() - start < timeout:
            pdfs = glob.glob(os.path.join(download_dir, nome_esperado))
            if pdfs:
                logger.info(f"PDF encontrado: {pdfs[0]}")
                return pdfs[0]
            logger.info(f"Aguardando PDF aparecer: {nome_esperado}")
            time.sleep(5)
        logger.error(
            f"Timeout: PDF {nome_esperado} não apareceu após {timeout}s"
        )
        return None

    @staticmethod
    def wait_for_spinner_and_dom_stable(
        driver, spinner_xpath, stable_time=5, timeout=60
    ):
        """
        Aguarda até que qualquer spinner desapareça e o DOM esteja estável

        Args:
            driver: Driver do Selenium
            spinner_xpath: XPath para buscar spinners/loaders
            stable_time: Tempo que o DOM deve ficar estável (sem mudanças)
            timeout: Tempo máximo total de espera

        Returns:
            True se o DOM estabilizou, False se ocorreu timeout
        """
        start = time.time()
        last_count = None
        stable_since = None
        consecutive_stable_counts = 0
        required_stable_counts = 3  # Número de verificações consecutivas onde o DOM deve estar estável
        
        logger.info(f"Aguardando spinner desaparecer e DOM estabilizar por {stable_time}s (timeout total: {timeout}s)")
        
        while time.time() - start < timeout:
            try:
                # Verifica se o spinner está visível
                spinners = driver.find_elements(By.XPATH, spinner_xpath)
                visible = (
                    any(s.is_displayed() for s in spinners) if spinners else False
                )
                if visible:
                    logger.info("Spinner ainda visível, aguardando...")
                    stable_since = None
                    consecutive_stable_counts = 0
                    time.sleep(1)  # Mais paciente ao esperar o spinner
                    continue
                    
                # Conta elementos relevantes para detectar estabilidade do DOM
                count_items = {
                    "links": len(driver.find_elements(By.TAG_NAME, "a")),
                    "buttons": len(driver.find_elements(By.TAG_NAME, "button")),
                    "inputs": len(driver.find_elements(By.TAG_NAME, "input")),
                    "divs": min(100, len(driver.find_elements(By.TAG_NAME, "div")))  # Limitar para não ficar muito pesado
                }
                count = sum(count_items.values())
                
                logger.info(f"Contagem atual de elementos: {count_items}")
                
                if last_count == count:
                    if stable_since is None:
                        stable_since = time.time()
                        logger.info("DOM começou a estabilizar")
                    
                    # Se o DOM está estável pelo tempo mínimo necessário
                    if time.time() - stable_since >= stable_time:
                        consecutive_stable_counts += 1
                        logger.info(f"DOM estável por {time.time() - stable_since:.1f}s (sequência: {consecutive_stable_counts}/{required_stable_counts})")
                        
                        # Se temos várias verificações consecutivas estáveis, considera estabilizado
                        if consecutive_stable_counts >= required_stable_counts:
                            logger.info(f"✅ DOM estável por {time.time() - stable_since:.1f}s e {consecutive_stable_counts} verificações consecutivas, pronto para interação.")
                            return True
                else:
                    if last_count is not None:
                        logger.info(f"DOM ainda instável: mudou de {last_count} para {count} elementos")
                    stable_since = None
                    consecutive_stable_counts = 0
                    
                last_count = count
                
            except Exception as e:
                logger.warning(f"Erro ao verificar estabilidade do DOM: {e}")
                # Continuar tentando mesmo com erro
            
            # Aguarda um pouco antes da próxima verificação
            time.sleep(0.5)
            
        logger.warning(
            f"Timeout esperando spinner sumir e DOM estabilizar por {stable_time}s (timeout total: {timeout}s)."
        )
        # Mesmo com timeout, tentar continuar a execução
        return False
