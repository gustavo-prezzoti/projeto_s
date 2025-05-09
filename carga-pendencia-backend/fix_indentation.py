#!/usr/bin/env python3
# Script para corrigir indentação em web_service.py

import re
import os
import tempfile
import shutil

def fix_indentation(filename):
    print(f"Corrigindo indentação em {filename}")
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Cria uma cópia de backup do arquivo original
    backup_file = filename + '.bak'
    shutil.copy2(filename, backup_file)
    print(f"Backup salvo como {backup_file}")
    
    # Lista das seções problemáticas a corrigir
    problematic_sections = [
        # HTML processing section com problemas de indentação
        r'# Processar o HTML.*?except Exception as bs_err:',
        
        # Seção com blocos try/except com identação irregular
        r'with open\(html_path.*?except Exception as html_err:',
        
        # Análise do status da dívida (possível problemas)
        r'# Análise automática do status da dívida.*?logger\.info\(f"Análise do texto:',
    ]
    
    # Corrigir cada seção
    fixed_content = content
    for pattern in problematic_sections:
        section_match = re.search(pattern, fixed_content, re.DOTALL)
        if section_match:
            print(f"Encontrada seção problemática: {pattern[:50]}...")
            problematic_section = section_match.group(0)
            
            # Corrigir as linhas
            fixed_lines = []
            for line in problematic_section.split('\n'):
                original_line = line
                
                # Remover excesso de espaços que causam indentação irregular
                line_stripped = line.strip()
                if not line_stripped:
                    fixed_lines.append('')
                    continue
                
                # Ajustar níveis de indentação
                if line_stripped.startswith(('try:', 'except', 'else:')):
                    # Blocos try/except com identação consistente
                    spaces = ' ' * (original_line.find(line_stripped) - 4)
                    fixed_line = spaces + line_stripped
                elif line_stripped.startswith('if ') and 'os.path.exists' in line_stripped:
                    # Blocos condicionais if dentro das exceções
                    spaces = ' ' * (original_line.find(line_stripped) - 4)
                    fixed_line = spaces + line_stripped
                elif line_stripped.startswith('for ') and 'screenshot' in line_stripped:
                    # Loops for dentro de blocos
                    spaces = ' ' * (original_line.find(line_stripped) - 4) 
                    fixed_line = spaces + line_stripped
                else:
                    # Manter indentação original para outras linhas
                    fixed_line = original_line
                
                fixed_lines.append(fixed_line)
            
            fixed_section = '\n'.join(fixed_lines)
            fixed_content = fixed_content.replace(problematic_section, fixed_section)
    
    # Salvar o arquivo corrigido
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"Arquivo corrigido e salvo como {filename}")
    print(f"Se necessário, recupere o backup: {backup_file}")

if __name__ == "__main__":
    file_path = "app/services/web_service.py"
    if not os.path.exists(file_path):
        print(f"Arquivo não encontrado: {file_path}")
    else:
        fix_indentation(file_path) 