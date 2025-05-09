#!/usr/bin/env python3
# Script para converter HTML de certidões em PDF com aparência idêntica ao original

import os
import sys
import glob
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
import requests
import re
import base64
from urllib.parse import urljoin, urlparse
import traceback
from datetime import datetime

def is_url(url):
    """Verifica se a string é uma URL válida"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def download_resource(url, timeout=10):
    """Baixa um recurso da web (imagem, css, etc.)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"Erro ao baixar recurso {url}: {e}")
        return None

def extract_domain(url):
    """Extrai o domínio de uma URL"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return None

def check_wkhtmltopdf():
    """Verifica se o wkhtmltopdf está instalado"""
    try:
        result = subprocess.run(["wkhtmltopdf", "--version"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              check=False)
        if result.returncode == 0:
            return True
        return False
    except:
        return False

def process_html(html_path, output_html_path=None, base_url=None, remove_images=True):
    """
    Processa um arquivo HTML para garantir que o PDF gerado seja idêntico ao original
    
    Args:
        html_path: Caminho do arquivo HTML original
        output_html_path: Caminho para salvar o HTML processado
        base_url: URL base para recursos relativos
        remove_images: Se True, remove todas as imagens do HTML
        
    Returns:
        Caminho para o HTML processado
    """
    print(f"Processando HTML: {html_path}")
    
    if not output_html_path:
        output_html_path = html_path.replace(".html", "_processed.html")
    
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Tentar detectar a URL base
        if not base_url:
            url_match = re.search(r'https?://[^\s"\']+(?:serverexec|cloud\.el\.com\.br)[^\s"\']*', html_content, re.IGNORECASE)
            if url_match:
                detected_url = url_match.group(0)
                base_url = extract_domain(detected_url)
                print(f"URL base detectada: {base_url}")
            else:
                base_url = "https://gpi18.cloud.el.com.br"
                print(f"Usando URL base padrão: {base_url}")
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remover scripts para evitar interferência na renderização
        for script in soup.find_all("script"):
            if script.string and any(x in (script.string or "") for x in ["imprimir()", "window.print", "location.reload"]):
                script.decompose()
                print("Script de impressão automática removido")
        
        # Remover todas as imagens se solicitado
        if remove_images:
            for img in soup.find_all("img"):
                img.decompose()
            print("Todas as imagens removidas do HTML")
            
            # Remover também divs que possam conter marcas d'água como background
            for div in soup.find_all("div", class_=lambda x: x and ("marca" in x.lower() or "brasao" in x.lower() or "logo" in x.lower())):
                div.decompose()
            
            # Remover backgrounds de divs que possam conter imagens
            for div in soup.find_all("div", style=lambda x: x and "background" in x.lower()):
                if "style" in div.attrs:
                    style = div["style"]
                    div["style"] = re.sub(r'background[^;]*;', '', style)
        
        # Estilo específico para reproduzir fielmente o documento da imagem
        style_tag = soup.new_tag("style")
        style_tag.string = """
            @page {
                size: A4;
                margin: 15mm;
            }
            body {
                background-color: white !important;
                margin: 0;
                padding: 20px;
                font-family: Arial, sans-serif;
                color: black !important;
                line-height: 1.4;
            }
            #interface {
                background-color: white;
                position: relative !important;
                width: 100%;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                box-shadow: none !important;
                min-height: 900px;
            }
            .municipio {
                display: block;
                margin-bottom: 20px;
                text-align: center;
            }
            .documento {
                text-align: center;
                margin: 20px 0;
                font-weight: bold;
                font-size: 16pt;
            }
            .numero {
                text-align: center;
                margin: 10px 0;
                font-size: 12pt;
            }
            .contribuinte {
                margin-top: 30px;
                margin-bottom: 30px;
            }
            .contribuinte p {
                margin: 5px 0;
                line-height: 1.5;
            }
            /* Estilo específico para alinhar corretamente o CNPJ */
            .contribuinte td {
                padding: 5px 10px 5px 0;
                vertical-align: top;
                white-space: nowrap;
            }
            .contribuinte span.label {
                font-weight: normal;
                padding-right: 10px;
            }
            .contribuinte span.value {
                font-weight: normal;
            }
            .texto {
                margin-top: 20px;
                text-align: justify;
                line-height: 1.5;
            }
            .validade {
                margin-top: 20px;
                line-height: 1.5;
            }
            .observacao {
                margin-top: 10px;
                line-height: 1.5;
            }
            .chave {
                margin-top: 10px;
                line-height: 1.5;
            }
            .emissao {
                text-align: right;
                margin-top: 50px;
            }
            h3 {
                font-size: 16pt;
                margin: 15px 0;
            }
            
            /* Formatação específica para CNPJ */
            .cnpj-container {
                display: flex;
                justify-content: flex-start;
                align-items: baseline;
            }
            .cnpj-label {
                margin-right: 10px;
                min-width: 50px;
            }
            .cnpj-value {
                font-weight: normal;
            }
        """
        
        # Adicionar o estilo ao cabeçalho
        if soup.head:
            soup.head.append(style_tag)
        else:
            head_tag = soup.new_tag("head")
            head_tag.append(style_tag)
            if soup.html:
                soup.html.insert(0, head_tag)
        
        # Adicionar meta tags para melhorar a renderização
        meta_utf8 = soup.new_tag("meta")
        meta_utf8["charset"] = "utf-8"
        
        meta_viewport = soup.new_tag("meta")
        meta_viewport["name"] = "viewport"
        meta_viewport["content"] = "width=device-width, initial-scale=1, maximum-scale=1"
        
        if soup.head:
            soup.head.insert(0, meta_utf8)
            soup.head.insert(1, meta_viewport)
        
        # Formatar especificamente o CNPJ para garantir alinhamento correto
        # Procurar por texto "CNPJ" e formatar o elemento pai
        for cnpj_text in soup.find_all(text=lambda t: t and "CNPJ" in t):
            # Encontrar o elemento pai ou avô que contém o CNPJ
            parent = cnpj_text.parent
            if parent.name in ['span', 'p', 'div']:
                # Criar uma div com display flex para alinhar o CNPJ corretamente
                cnpj_div = soup.new_tag("div")
                cnpj_div['class'] = "cnpj-container"
                
                # Criar span para o label e valor
                cnpj_label = soup.new_tag("span")
                cnpj_label['class'] = "cnpj-label"
                cnpj_label.string = "CNPJ"
                
                cnpj_value = soup.new_tag("span")
                cnpj_value['class'] = "cnpj-value"
                
                # Extrair o número do CNPJ do texto
                cnpj_match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}', str(parent))
                if cnpj_match:
                    cnpj_value.string = cnpj_match.group(0)
                    
                    # Substituir o elemento original pelo novo formato
                    cnpj_div.append(cnpj_label)
                    cnpj_div.append(cnpj_value)
                    parent.replace_with(cnpj_div)
                    print("CNPJ reformatado para melhor alinhamento")
                
        # Salvar o HTML processado
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        
        print(f"HTML processado salvo em: {output_html_path}")
        return output_html_path
    
    except Exception as e:
        print(f"Erro ao processar HTML: {e}")
        traceback.print_exc()
        return html_path

def convert_to_pdf(html_path, pdf_path=None, landscape=False):
    """
    Converte HTML para PDF usando wkhtmltopdf com configurações específicas para
    reproduzir o visual idêntico ao documento da imagem
    
    Args:
        html_path: Caminho do arquivo HTML processado
        pdf_path: Caminho para o arquivo PDF de saída
        landscape: Se verdadeiro, gera o PDF em orientação paisagem
        
    Returns:
        Tuple: (sucesso, caminho_pdf)
    """
    if not pdf_path:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
        
    print(f"Convertendo {html_path} para PDF: {pdf_path}")
    
    # Verificar se o wkhtmltopdf está instalado
    if not check_wkhtmltopdf():
        print("wkhtmltopdf não encontrado! Por favor, instale: https://wkhtmltopdf.org/downloads.html")
        return False, None
    
    try:
        # Definir argumentos básicos
        args = [
            "wkhtmltopdf",
            "--encoding", "utf-8",
            "--page-size", "A4",
            "--dpi", "300",
            "--no-images",  # Desabilitar imagens explicitamente
            "--no-background",  # Remover backgrounds
            "--enable-javascript",
            "--javascript-delay", "1000",
            "--disable-smart-shrinking",
            "--enable-local-file-access",
            "--print-media-type",
            "--margin-top", "15mm",
            "--margin-bottom", "15mm",
            "--margin-left", "15mm",
            "--margin-right", "15mm",
        ]
        
        # Adicionar opção de paisagem se necessário
        if landscape:
            args.append("--orientation")
            args.append("Landscape")
        
        # Criar CSS temporário para estilo adicional
        with tempfile.NamedTemporaryFile(suffix='.css', delete=False, mode='w', encoding='utf-8') as css_file:
            css_path = css_file.name
            css_file.write("""
                body {
                    background-color: white !important;
                    color: black !important;
                    font-family: Arial, sans-serif;
                }
                #interface {
                    position: relative !important;
                    background-color: white !important;
                    padding: 20px;
                }
                img {
                    display: none !important;
                }
                .municipio {
                    display: block !important;
                    text-align: center !important;
                }
                /* Formatação específica para CNPJ */
                .cnpj-container {
                    display: flex !important;
                    justify-content: flex-start !important;
                    align-items: baseline !important;
                }
                .cnpj-label {
                    margin-right: 10px !important;
                    min-width: 50px !important;
                }
                .cnpj-value {
                    font-weight: normal !important;
                }
            """)
        
        # Adicionar o CSS temporário aos argumentos
        args.extend(["--user-style-sheet", css_path])
        
        # Adicionar os caminhos dos arquivos de entrada e saída
        args.extend([html_path, pdf_path])
        
        # Executar o wkhtmltopdf
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        
        # Remover o arquivo CSS temporário
        try:
            os.unlink(css_path)
        except:
            pass
        
        # Verificar se o PDF foi gerado
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            print(f"✅ PDF gerado com sucesso: {pdf_path}")
            return True, pdf_path
        else:
            error = result.stderr.decode()
            print(f"❌ Falha ao gerar PDF: {error}")
            
            # Tentar método alternativo
            print("Tentando método alternativo...")
            alt_args = args.copy()
            
            # Remover algumas opções que podem estar causando problemas
            filtered_args = [arg for arg in alt_args if "--disable-smart-shrinking" not in arg]
            
            alt_result = subprocess.run(filtered_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF gerado com sucesso (método alternativo): {pdf_path}")
                return True, pdf_path
            else:
                alt_error = alt_result.stderr.decode()
                print(f"❌ Falha ao gerar PDF (método alternativo): {alt_error}")
                return False, None
    
    except Exception as e:
        print(f"❌ Erro na conversão: {e}")
        traceback.print_exc()
        return False, None

def process_directory(dir_path, pattern="*.html", remove_images=True):
    """
    Processa todos os arquivos HTML em um diretório
    
    Args:
        dir_path: Caminho do diretório contendo arquivos HTML
        pattern: Padrão de arquivos a serem processados
        remove_images: Se True, remove todas as imagens dos PDFs
        
    Returns:
        Tuple: (sucessos, falhas, lista_pdfs)
    """
    if not os.path.isdir(dir_path):
        print(f"Diretório não encontrado: {dir_path}")
        return 0, 0, []
    
    # Criar diretório de saída para os PDFs
    pdf_dir = os.path.join(os.getcwd(), "document")
    os.makedirs(pdf_dir, exist_ok=True)
    
    # Encontrar todos os arquivos HTML
    html_files = glob.glob(os.path.join(dir_path, pattern))
    
    if not html_files:
        print(f"Nenhum arquivo HTML encontrado com o padrão {pattern} em {dir_path}")
        return 0, 0, []
    
    print(f"Encontrados {len(html_files)} arquivos HTML para processar.")
    
    sucessos = 0
    falhas = 0
    pdfs_gerados = []
    
    for html_file in html_files:
        try:
            # Criar nome para o arquivo processado
            base_name = os.path.basename(html_file)
            processed_html = os.path.join(dir_path, f"processed_{base_name}")
            
            # Processar o HTML
            processed_html = process_html(html_file, processed_html, remove_images=remove_images)
            
            # Definir nome do PDF (na pasta document/)
            pdf_name = os.path.splitext(os.path.basename(html_file))[0] + ".pdf"
            pdf_path = os.path.join(pdf_dir, pdf_name)
            
            # Converter para PDF
            success, pdf_output = convert_to_pdf(processed_html, pdf_path)
            
            if success:
                sucessos += 1
                pdfs_gerados.append(pdf_output)
            else:
                falhas += 1
        
        except Exception as e:
            print(f"Erro ao processar {html_file}: {e}")
            traceback.print_exc()
            falhas += 1
    
    return sucessos, falhas, pdfs_gerados

def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description="Converte HTML de certidões para PDF com visual idêntico ao original")
    parser.add_argument("--dir", help="Diretório contendo arquivos HTML (default: screenshots)", default="screenshots")
    parser.add_argument("--pattern", help="Padrão de arquivos a processar (default: *_new_tab_html.html)", default="*_new_tab_html.html")
    parser.add_argument("--file", help="Arquivo HTML específico para converter")
    parser.add_argument("--output", help="Arquivo PDF de saída (quando usando --file)")
    parser.add_argument("--base-url", help="URL base para recursos relativos")
    parser.add_argument("--landscape", help="Gerar PDF em orientação paisagem", action="store_true")
    parser.add_argument("--keep-images", help="Manter imagens no PDF (padrão é remover)", action="store_true")
    
    args = parser.parse_args()
    
    # Verificar se wkhtmltopdf está instalado
    if not check_wkhtmltopdf():
        print("\nÉ necessário instalar wkhtmltopdf para converter HTML em PDF.")
        print("Por favor, baixe e instale em: https://wkhtmltopdf.org/downloads.html")
        return
    
    # Flag para remover ou manter imagens (padrão é remover)
    remove_images = not args.keep_images
    if remove_images:
        print("Imagens serão removidas dos PDFs gerados")
    else:
        print("Imagens serão mantidas nos PDFs gerados")
    
    # Processar um único arquivo
    if args.file:
        if not os.path.exists(args.file):
            print(f"Arquivo não encontrado: {args.file}")
            return
        
        # Processar o HTML
        processed_html = process_html(args.file, base_url=args.base_url, remove_images=remove_images)
        
        # Definir arquivo de saída
        pdf_output = args.output if args.output else os.path.splitext(args.file)[0] + ".pdf"
        
        # Converter para PDF
        success, pdf_path = convert_to_pdf(processed_html, pdf_output, args.landscape)
        
        if success:
            print(f"\nPDF gerado com sucesso: {pdf_path}")
        else:
            print("\nFalha ao gerar PDF.")
    
    # Processar um diretório
    else:
        sucessos, falhas, pdfs = process_directory(args.dir, args.pattern, remove_images=remove_images)
        print(f"\nResumo: {sucessos} conversões bem-sucedidas, {falhas} falhas")
        if sucessos > 0:
            print(f"PDFs gerados em: {os.path.join(os.getcwd(), 'document')}")
            for pdf in pdfs[:5]:  # Mostrar até 5 PDFs
                print(f" - {os.path.basename(pdf)}")
            if len(pdfs) > 5:
                print(f" ... e mais {len(pdfs) - 5} arquivo(s)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperação interrompida pelo usuário")
    except Exception as e:
        print(f"Erro não tratado: {e}")
        traceback.print_exc() 