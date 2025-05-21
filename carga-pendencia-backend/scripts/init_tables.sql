-- Create CNPJ table
CREATE TABLE IF NOT EXISTS cnpjs (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(14) NOT NULL UNIQUE,
    razao_social VARCHAR(255),
    municipio VARCHAR(255),
    status VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on CNPJ table
CREATE INDEX IF NOT EXISTS idx_cnpjs_cnpj ON cnpjs(cnpj);

-- Create Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    nome VARCHAR(100),
    email VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on Users table
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Create Queue table
CREATE TABLE IF NOT EXISTS fila_cnpj (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(14) NOT NULL,
    razao_social VARCHAR(255),
    municipio VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pendente',
    resultado TEXT,
    status_divida VARCHAR(50),
    pdf_path VARCHAR(255),
    failures INTEGER DEFAULT 0,
    error_message TEXT,
    user_id INTEGER,
    full_result TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indices on Queue table
CREATE INDEX IF NOT EXISTS idx_fila_cnpj_cnpj ON fila_cnpj(cnpj);
CREATE INDEX IF NOT EXISTS idx_fila_cnpj_status ON fila_cnpj(status);
CREATE INDEX IF NOT EXISTS idx_fila_cnpj_user_id ON fila_cnpj(user_id);

-- Create Ignore list table
CREATE TABLE IF NOT EXISTS fila_cnpj_ignorados (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(14) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on Ignore list table
CREATE INDEX IF NOT EXISTS idx_fila_cnpj_ignorados_cnpj ON fila_cnpj_ignorados(cnpj); 