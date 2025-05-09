# CNPJ Processor

Sistema para processamento automatizado de CNPJs e consulta de certidões.

## Requisitos

- **Python 3.11** (obrigatório esta versão específica)
- Docker Desktop
- Conexão com a internet

## Instalação

### Opção 1: Executar scripts de configuração (Recomendado)

1. Instale o Python 3.11 do site oficial: https://www.python.org/downloads/release/python-3113/
2. Instale o Docker Desktop: https://www.docker.com/products/docker-desktop/
3. Clone ou baixe este repositório
4. Execute o script de configuração do ambiente:
   ```
   setup_environment.bat
   ```
5. Execute o script de compilação do executável:
   ```
   rebuild_exe.bat
   ```
6. O executável será gerado na pasta `dist\CNPJ Processor\`

### Opção 2: Instalação manual

1. Instale o Python 3.11
2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
3. Instale o Docker Desktop
4. Execute o programa diretamente:
   ```
   python app_gui.py
   ```

## Solução de problemas

### Erro de compilação do executável

Se você encontrar erros como `PermissionError: [WinError 32] O arquivo já está sendo usado por outro processo`:

1. Execute o script de limpeza para encerrar processos e remover arquivos:
   ```
   clean_dist.bat
   ```
2. Depois tente recompilar novamente:
   ```
   rebuild_exe.bat
   ```

Se o problema persistir:
1. Reinicie o computador
2. Verifique se não há outros processos Python em execução
3. Execute o sistema como administrador

### Erro de compatibilidade numpy/pandas

Se você encontrar erros como `ValueError: numpy.dtype size changed, may indicate binary incompatibility`, execute:

```
pip uninstall -y numpy pandas
pip install numpy==1.24.3
pip install pandas==2.0.3
```

### Erro de conexão com RabbitMQ ou MySQL

Se você ver erros como `socket.gaierror: [Errno 11001] getaddrinfo failed` ou problemas de conexão com hosts `rabbitmq-cnpj` ou `mysql-cnpj`:

1. O sistema foi atualizado para detectar automaticamente o ambiente e usar o endereço correto ('localhost' ou nome do container Docker)
2. Se ainda houver problemas, verifique:
   - Se os containers Docker estão em execução com `docker ps`
   - Tente reiniciar o Docker Desktop
   - Verifique se as portas 5672 (RabbitMQ) e 3306 (MySQL) estão disponíveis
   - Se estiver usando VPN, pode ser necessário desabilitá-la

### Erros ao conectar com o Docker

- Certifique-se de que o Docker Desktop está em execução
- Se houver erro, tente limpar todos os containers, volumes e imagens:
  ```
  docker system prune -a --volumes
  ```

### Erro ao iniciar a API

- Verifique se todas as dependências foram instaladas corretamente
- Certifique-se de que está usando Python 3.11
- Verifique se os serviços de Docker estão funcionando:
  ```
  docker ps
  ```

## Estrutura do Projeto

- `app_gui.py` - Interface gráfica principal
- `worker_cnpj.py` - Worker que processa CNPJs da fila
- `app/` - Pasta com o backend da aplicação
  - `main.py` - Ponto de entrada da API
  - `models/` - Modelos de dados
  - `services/` - Serviços para processamento de CNPJs

## Docker

O sistema utiliza dois containers Docker:
- `mysql-cnpj` - Banco de dados MySQL
- `rabbitmq-cnpj` - Message broker RabbitMQ

A comunicação entre a aplicação e os serviços é feita usando os nomes dos containers como host, com detecção automática de ambiente para conexões localhost quando necessário.

## Execução do sistema compilado

1. Extraia o pacote ZIP
2. Execute `CNPJ Processor.exe`
3. Clique em "Iniciar Sistema"
4. Aguarde a inicialização dos containers Docker
5. O sistema estará disponível em http://localhost:8000

## Notas importantes

- Os containers Docker devem estar em execução antes de iniciar o worker
- O sistema cria pastas para armazenar arquivos temporários e resultados
- Certifique-se de ter permissões de administrador se necessário 