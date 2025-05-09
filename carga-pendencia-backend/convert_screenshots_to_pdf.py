#!/usr/bin/env python3
# Script para converter os HTML da pasta screenshots para PDF

import os
import sys
import glob
import argparse
import traceback
from pathlib import Path

def convert_html_to_pdf(html_path, pdf_path=None):
    """
    Converte um arquivo HTML em PDF usando vários métodos disponíveis
    
    Args:
        html_path (str): Caminho do arquivo HTML
        pdf_path (str, optional): Caminho de saída do PDF. Se None, usa o mesmo nome do HTML mas com extensão .pdf
        
    Returns:
        tuple: (sucesso, caminho_pdf, mensagem)
    """
    if not os.path.exists(html_path):
        return False, None, f"Arquivo HTML não encontrado: {html_path}"
        
    # Se pdf_path não for especificado, criar baseado no html_path
    if not pdf_path:
        pdf_path = os.path.splitext(html_path)[0] + ".pdf"
        
    # Tentar diferentes métodos para converter HTML para PDF
    
    # Método 1: Usando wkhtmltopdf se disponível
    try:
        import subprocess
        wkhtmltopdf_path = "wkhtmltopdf"  # Assumindo que está no PATH
        
        # Verificar se wkhtmltopdf está instalado
        try:
            subprocess.run([wkhtmltopdf_path, "--version"], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE, 
                          check=False)
                          
            # Converter HTML para PDF
            result = subprocess.run([wkhtmltopdf_path, 
                                  "--encoding", "utf-8",
                                  "--page-size", "A4",
                                  "--margin-top", "10mm",
                                  "--margin-bottom", "10mm",
                                  "--margin-left", "10mm",
                                  "--margin-right", "10mm",
                                  html_path, pdf_path], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, 
                                  check=False)
            
            if os.path.exists(pdf_path):
                return True, pdf_path, "PDF criado com sucesso usando wkhtmltopdf"
        except Exception as wk_err:
            print(f"Não foi possível usar wkhtmltopdf: {wk_err}")
    except Exception as e:
        print(f"Erro ao tentar usar wkhtmltopdf: {e}")
    
    # Método 2: Usando pdfkit (também requer wkhtmltopdf instalado, mas com interface Python)
    try:
        import pdfkit
        options = {
            'page-size': 'A4',
            'margin-top': '10mm',
            'margin-right': '10mm',
            'margin-bottom': '10mm',
            'margin-left': '10mm',
            'encoding': 'UTF-8',
        }
        pdfkit.from_file(html_path, pdf_path, options=options)
        if os.path.exists(pdf_path):
            return True, pdf_path, "PDF criado com sucesso usando pdfkit"
    except Exception as pk_err:
        print(f"Não foi possível usar pdfkit: {pk_err}")
    
    # Método 3: Usando weasyprint
    try:
        import weasyprint
        weasyprint.HTML(filename=html_path).write_pdf(pdf_path)
        if os.path.exists(pdf_path):
            return True, pdf_path, "PDF criado com sucesso usando weasyprint"
    except Exception as wp_err:
        print(f"Não foi possível usar weasyprint: {wp_err}")
    
    # Se chegou aqui, nenhum método funcionou
    return False, None, "Não foi possível converter HTML para PDF com nenhum método disponível"

def main():
    # Diretório de screenshots padrão
    screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
    
    # Verificar se o diretório existe
    if not os.path.isdir(screenshots_dir):
        print(f"Diretório de screenshots não encontrado: {screenshots_dir}")
        return
        
    # Encontrar todos os arquivos HTML
    html_files = glob.glob(os.path.join(screenshots_dir, "*_new_tab_html.html"))
    html_files += glob.glob(os.path.join(screenshots_dir, "*_page_html.html"))
    
    if not html_files:
        print(f"Nenhum arquivo HTML encontrado em: {screenshots_dir}")
        return
        
    print(f"Encontrados {len(html_files)} arquivos HTML para converter em PDF")
    
    # Converter cada arquivo HTML para PDF
    sucessos = 0
    falhas = 0
    
    for html_file in html_files:
        try:
            # Criar nome do arquivo PDF baseado no HTML
            pdf_file = os.path.splitext(html_file)[0] + ".pdf"
            
            print(f"Convertendo: {html_file} -> {pdf_file}")
            
            # Tentar converter
            sucesso, pdf_path, mensagem = convert_html_to_pdf(html_file, pdf_file)
            
            if sucesso:
                print(f"✅ {mensagem}: {pdf_path}")
                sucessos += 1
            else:
                print(f"❌ {mensagem}")
                falhas += 1
        except Exception as e:
            print(f"❌ Erro ao processar {html_file}: {e}")
            falhas += 1
    
    print(f"\nResumo: {sucessos} conversões bem-sucedidas, {falhas} falhas")
    
    # Caso não tenha funcionado, mostrar informações sobre como instalar as dependências
    if falhas > 0:
        print("\nPara converter HTML em PDF, você pode instalar uma destas ferramentas:")
        print("1. wkhtmltopdf: https://wkhtmltopdf.org/downloads.html")
        print("2. pdfkit (Python): pip install pdfkit")
        print("3. weasyprint (Python): pip install weasyprint")
        print("\nObs: pdfkit requer o wkhtmltopdf instalado. Weasyprint tem suas próprias dependências.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperação interrompida pelo usuário")
    except Exception as e:
        print(f"Erro não tratado: {e}")
        traceback.print_exc() 