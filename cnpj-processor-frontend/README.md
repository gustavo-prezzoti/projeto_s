# CNPJ Processor Frontend

Interface de usuário para o sistema de processamento de CNPJs.

## Funcionalidades

- Upload de arquivos Excel com CNPJs para processamento
- Consulta de CNPJs processados com filtros por status e data
- Monitoramento em tempo real do processamento
- Reprocessamento de CNPJs com erro

## Tecnologias Utilizadas

- React
- React Router
- Axios
- React Icons
- CSS Puro

## Instalação

1. Certifique-se de ter o Node.js instalado em sua máquina
2. Clone este repositório
3. Navegue até a pasta do projeto
4. Instale as dependências:

```bash
npm install
```

## Executando o Projeto

Para iniciar o servidor de desenvolvimento:

```bash
npm run dev
```

O aplicativo estará disponível em `http://localhost:5173`

## Construindo para Produção

Para gerar uma versão de produção:

```bash
npm run build
```

Os arquivos serão gerados na pasta `dist`.

## Estrutura do Projeto

```
src/
├── components/      # Componentes reutilizáveis
├── pages/           # Páginas da aplicação
├── services/        # Serviços e APIs
├── App.jsx          # Componente principal
├── App.css          # Estilos do componente principal
├── main.jsx         # Ponto de entrada da aplicação
└── index.css        # Estilos globais
```

## Backend

Este frontend se comunica com uma API RESTful. Certifique-se de que o backend esteja em execução na porta 8000.

## Configuração

O endereço do backend pode ser configurado no arquivo `src/services/api.js`.
