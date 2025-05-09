#!/usr/bin/env python3
# Utilitário para verificar a instalação do wkhtmltopdf

import os
import sys
import subprocess
import platform
import tempfile

def check_wkhtmltopdf():
    """Verifica se o wkhtmltopdf está instalado e funcionando corretamente"""
    print("Verificando instalação do wkhtmltopdf...")
    
    try:
        # Verifica se o comando existe no PATH
        result = subprocess.run(["wkhtmltopdf", "--version"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              check=False)
        
        if result.returncode == 0:
            version = result.stdout.decode().strip()
            print(f"✅ wkhtmltopdf está instalado: {version}")
            
            # Testar geração de PDF
            print("\nTestando geração de PDF...")
            
            # Criar um arquivo HTML temporário
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
                html_path = f.name
                f.write("""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Teste wkhtmltopdf</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 40px; }
                        h1 { color: #2c3e50; }
                        .container { border: 1px solid #ddd; padding: 20px; }
                    </style>
                </head>
                <body>
                    <h1>Teste do wkhtmltopdf</h1>
                    <div class="container">
                        <p>Se você está vendo este arquivo PDF, a instalação do wkhtmltopdf está funcionando corretamente!</p>
                        <p>Data do teste: <strong>""" + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</strong></p>
                    </div>
                </body>
                </html>
                """)
            
            # Definir arquivo PDF de saída
            pdf_path = os.path.join(os.getcwd(), "teste_wkhtmltopdf.pdf")
            
            # Gerar PDF
            convert_result = subprocess.run(["wkhtmltopdf", 
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
            
            # Limpar arquivo HTML temporário
            try:
                os.unlink(html_path)
            except:
                pass
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                print(f"✅ PDF gerado com sucesso: {pdf_path}")
                print("\nA instalação do wkhtmltopdf está correta e funcional!")
                return True
            else:
                print(f"❌ Falha ao gerar PDF. Erro: {convert_result.stderr.decode()}")
        else:
            print(f"❌ wkhtmltopdf não está instalado ou não está no PATH")
            print(f"Erro: {result.stderr.decode()}")
    except Exception as e:
        print(f"❌ Erro ao verificar wkhtmltopdf: {str(e)}")
    
    print("\nInstruções para instalar wkhtmltopdf:")
    system = platform.system().lower()
    
    if "win" in system:
        print("\nWindows:")
        print("1. Baixe o instalador em: https://wkhtmltopdf.org/downloads.html")
        print("2. Execute o instalador e siga as instruções")
        print("3. Importante: Selecione a opção para adicionar ao PATH durante a instalação")
        print("4. Reinicie seu terminal/prompt de comando após a instalação")
    
    elif "linux" in system:
        print("\nLinux (Debian/Ubuntu):")
        print("1. Execute: sudo apt-get update")
        print("2. Execute: sudo apt-get install -y wkhtmltopdf")
        
        print("\nLinux (CentOS/RHEL):")
        print("1. Execute: sudo yum install -y wkhtmltopdf")
    
    elif "darwin" in system:
        print("\nmacOS:")
        print("1. Se tiver o Homebrew instalado, execute: brew install wkhtmltopdf")
        print("2. Ou baixe o instalador em: https://wkhtmltopdf.org/downloads.html")
    
    else:
        print(f"\nSistema {system} não reconhecido:")
        print("Por favor, visite https://wkhtmltopdf.org/downloads.html para baixar o instalador correto")
    
    return False

if __name__ == "__main__":
    try:
        check_wkhtmltopdf()
    except KeyboardInterrupt:
        print("\nVerificação interrompida pelo usuário")
    except Exception as e:
        print(f"Erro não tratado: {e}") 