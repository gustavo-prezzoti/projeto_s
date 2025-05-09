#!/usr/bin/env python3
# Script para melhorar a conversão de HTML de certidões para PDF

import os
import sys
import glob
import argparse
import subprocess
import traceback
import base64
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse
import tempfile

def is_url(url):
    """
    Verifica se a string é uma URL
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def download_resource(url, timeout=10):
    """
    Baixa um recurso externo (imagem, css, etc)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"Erro ao baixar recurso {url}: {e}")
        return None

def resource_to_base64(content, content_type):
    """
    Converte o conteúdo para base64
    """
    try:
        b64content = base64.b64encode(content).decode('utf-8')
        return f"data:{content_type};base64,{b64content}"
    except Exception as e:
        print(f"Erro ao converter para base64: {e}")
        return None

def extract_domain(url):
    """
    Extrai o domínio de uma URL
    """
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return None

def process_html(html_path, base_url=None):
    """
    Processa o arquivo HTML para melhorar a geração do PDF
    
    Args:
        html_path: Caminho do arquivo HTML
        base_url: URL base para recursos relativos
        
    Returns:
        Caminho do arquivo HTML processado
    """
    print(f"Processando HTML: {html_path}")
    
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Tente detectar a URL base analisando o conteúdo HTML
        if not base_url:
            # Tentar encontrar URLs no HTML para determinar a base
            url_match = re.search(r'https?://[^\s"\']+(?:serverexec|cloud\.el\.com\.br)[^\s"\']*', html_content, re.IGNORECASE)
            if url_match:
                detected_url = url_match.group(0)
                base_url = extract_domain(detected_url)
                print(f"URL base detectada: {base_url}")
            else:
                base_url = "https://gpi18.cloud.el.com.br"
                print(f"Usando URL base padrão: {base_url}")
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remover script de impressão automática
        for script in soup.find_all("script"):
            if script.string and "imprimir()" in script.string:
                script.decompose()
                print("Script de impressão automática removido")
        
        # Processar todas as imagens para converter em base64 ou usar URLs absolutas
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
                
            # Se src já é uma URL completa
            if is_url(src):
                img_url = src
            # Se src é uma URL relativa
            elif src.startswith("/"):
                img_url = urljoin(base_url, src)
            # Se src já é um data:image
            elif src.startswith("data:"):
                continue
            else:
                img_url = urljoin(base_url, src)
            
            # Baixar a imagem e converter para base64
            print(f"Baixando imagem: {img_url}")
            img_data = download_resource(img_url)
            if img_data:
                # Determinar o tipo de conteúdo
                content_type = "image/jpeg"  # padrão
                if img_url.lower().endswith(".png"):
                    content_type = "image/png"
                elif img_url.lower().endswith(".gif"):
                    content_type = "image/gif"
                elif img_url.lower().endswith(".svg"):
                    content_type = "image/svg+xml"
                
                # Converter para base64
                b64_data = resource_to_base64(img_data, content_type)
                if b64_data:
                    img["src"] = b64_data
                    print(f"Imagem convertida para base64: {img_url[:50]}...")
                else:
                    img["src"] = img_url
                    print(f"Não foi possível converter imagem para base64, usando URL absoluta: {img_url}")
            else:
                img["src"] = img_url
                print(f"Não foi possível baixar imagem, usando URL absoluta: {img_url}")
        
        # Melhorar estilo para impressão e PDF
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
            }
            #interface { 
                background-color: white; 
                position: relative !important; 
                width: 100%; 
                max-width: 800px; 
                margin: 0 auto; 
                padding: 20px; 
                box-shadow: none !important;
            }
            .municipio { 
                display: flex; 
                align-items: center; 
                margin-bottom: 20px; 
            }
            .municipio img { 
                width: 80px; 
                display: block !important;
            }
            .documento { 
                text-align: center; 
                margin: 20px 0; 
            }
            .detalhe { 
                display: flex; 
                width: 100%; 
                margin-bottom: 15px; 
            }
            .texto { 
                margin-top: 20px; 
                line-height: 1.5; 
            }
            img[style*='opacity'] { 
                opacity: 0.3 !important; 
                display: block !important;
            }
            div[style*='position: absolute'] { 
                position: relative !important; 
            }
            h3 { 
                font-size: 16pt; 
                margin: 15px 0;
            }
            p {
                margin: 8px 0;
                line-height: 1.4;
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
        
        # Adicionar título para melhorar a identificação
        title_tag = soup.new_tag("title")
        title_tag.string = f"Certidão - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if soup.head:
            # Remover título existente, se houver
            if soup.head.title:
                soup.head.title.decompose()
            soup.head.append(title_tag)
        
        # Garantir que o conteúdo principal esteja visível
        for div in soup.find_all("div", id="interface"):
            # Remover qualquer estilo problemático
            if "style" in div.attrs:
                style = div["style"]
                style = style.replace("position: absolute", "position: relative")
                div["style"] = style
        
        # Salvar HTML processado
        processed_html_path = html_path.replace(".html", "_processed.html")
        with open(processed_html_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        
        print(f"HTML processado salvo em: {processed_html_path}")
        return processed_html_path
    
    except Exception as e:
        print(f"Erro ao processar HTML: {e}")
        traceback.print_exc()
        return html_path

def convert_to_pdf(html_path, pdf_path=None):
    """
    Converte o HTML processado para PDF usando wkhtmltopdf com opções otimizadas
    
    Args:
        html_path: Caminho do arquivo HTML processado
        pdf_path: Caminho para o arquivo PDF de saída (opcional)
        
    Returns:
        Tuple: (sucesso, caminho_pdf)
    """
    if not pdf_path:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
    
    print(f"Convertendo {html_path} para PDF: {pdf_path}")
    
    try:
        # Verificar se o wkhtmltopdf está instalado
        verify_result = subprocess.run(
            ["wkhtmltopdf", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            check=False
        )
        
        if verify_result.returncode != 0:
            print("wkhtmltopdf não encontrado. Por favor, instale: https://wkhtmltopdf.org/downloads.html")
            return False, None
        
        # Converter HTML para PDF com opções otimizadas
        convert_result = subprocess.run([
            "wkhtmltopdf",
            "--encoding", "utf-8",
            "--page-size", "A4",
            "--margin-top", "10mm",
            "--margin-bottom", "10mm",
            "--margin-left", "10mm",
            "--margin-right", "10mm",
            "--dpi", "300",  # Maior qualidade
            "--image-quality", "100",  # Melhor qualidade de imagem
            "--enable-javascript",
            "--javascript-delay", "1000",  # Aguardar JavaScript carregar
            "--disable-smart-shrinking",  # Evitar redimensionamento que pode causar problemas
            "--enable-local-file-access",  # Permitir acesso a arquivos locais
            "--print-media-type",  # Usar CSS de impressão
            "--no-outline",  # Sem índice
            html_path, pdf_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            print(f"✅ PDF gerado com sucesso: {pdf_path}")
            return True, pdf_path
        else:
            error = convert_result.stderr.decode()
            print(f"❌ Falha ao gerar PDF: {error}")
            
            # Tentar abordagem alternativa com a opção --user-style-sheet
            print("Tentando abordagem alternativa...")
            
            # Criar um arquivo CSS temporário com estilos avançados
            with tempfile.NamedTemporaryFile(suffix='.css', delete=False, mode='w', encoding='utf-8') as css_file:
                css_path = css_file.name
                css_file.write("""
                    @page {
                        size: A4;
                        margin: 15mm;
                    }
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
                        display: block !important;
                    }
                    img[style*='opacity'] {
                        opacity: 0.3 !important;
                    }
                    div[style*='position: absolute'] {
                        position: relative !important;
                    }
                """)
            
            # Tentar converter novamente com o CSS personalizado
            alt_convert_result = subprocess.run([
                "wkhtmltopdf",
                "--encoding", "utf-8",
                "--page-size", "A4",
                "--user-style-sheet", css_path,
                "--no-background",
                "--enable-javascript",
                "--javascript-delay", "1000",
                "--disable-smart-shrinking",
                "--enable-local-file-access",
                "--print-media-type",
                html_path, pdf_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            
            # Remover arquivo CSS temporário
            try:
                os.unlink(css_path)
            except:
                pass
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF gerado com sucesso na segunda tentativa: {pdf_path}")
                return True, pdf_path
            else:
                error = alt_convert_result.stderr.decode()
                print(f"❌ Falha na segunda tentativa: {error}")
                return False, None
    
    except Exception as e:
        print(f"❌ Erro na conversão: {e}")
        traceback.print_exc()
        return False, None

def main():
    parser = argparse.ArgumentParser(description="Converter HTML de certidões para PDF com melhor qualidade")
    parser.add_argument("--dir", help="Diretório onde procurar arquivos HTML (default: screenshots)", default="screenshots")
    parser.add_argument("--output", help="Diretório de saída para PDFs (default: document)", default="document")
    parser.add_argument("--pattern", help="Padrão de arquivos a processar (default: *_new_tab_html.html)", default="*_new_tab_html.html")
    parser.add_argument("--file", help="Arquivo HTML específico para converter")
    parser.add_argument("--base-url", help="URL base para recursos", default=None)
    
    args = parser.parse_args()
    
    if args.file:
        # Processar um arquivo específico
        if not os.path.exists(args.file):
            print(f"Arquivo não encontrado: {args.file}")
            return
        
        # Criar diretório de saída se não existir
        os.makedirs(args.output, exist_ok=True)
        
        # Processar HTML e converter para PDF
        processed_html = process_html(args.file, args.base_url)
        pdf_name = os.path.splitext(os.path.basename(args.file))[0] + ".pdf"
        pdf_path = os.path.join(args.output, pdf_name)
        success, _ = convert_to_pdf(processed_html, pdf_path)
        
        if success:
            print(f"Conversão concluída. PDF salvo em: {pdf_path}")
        else:
            print("Falha na conversão.")
    else:
        # Processar todos os arquivos do diretório que correspondam ao padrão
        if not os.path.isdir(args.dir):
            print(f"Diretório não encontrado: {args.dir}")
            return
        
        # Criar diretório de saída se não existir
        os.makedirs(args.output, exist_ok=True)
        
        # Encontrar todos os arquivos HTML que correspondam ao padrão
        html_files = glob.glob(os.path.join(args.dir, args.pattern))
        
        if not html_files:
            print(f"Nenhum arquivo encontrado com o padrão {args.pattern} em {args.dir}")
            return
        
        print(f"Encontrados {len(html_files)} arquivos para processar.")
        
        sucessos = 0
        falhas = 0
        
        for html_file in html_files:
            try:
                # Processar HTML
                processed_html = process_html(html_file, args.base_url)
                
                # Converter para PDF
                pdf_name = os.path.splitext(os.path.basename(html_file))[0] + ".pdf"
                pdf_path = os.path.join(args.output, pdf_name)
                
                success, _ = convert_to_pdf(processed_html, pdf_path)
                
                if success:
                    sucessos += 1
                else:
                    falhas += 1
            except Exception as e:
                print(f"Erro ao processar {html_file}: {e}")
                traceback.print_exc()
                falhas += 1
        
        print(f"\nResumo: {sucessos} conversões bem-sucedidas, {falhas} falhas")

if __name__ == "__main__":
    main() 