<?php
/**
 * Cria as tabelas da fila e usuario. Execute uma vez: php init_db.php
 */
$config = require __DIR__ . '/config.php';
$dbConfig = $config['db'];

$dsn = sprintf(
    'pgsql:host=%s;port=%s;dbname=%s',
    $dbConfig['host'],
    $dbConfig['port'],
    $dbConfig['database']
);
$pdo = new PDO($dsn, $dbConfig['user'], $dbConfig['password']);
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

$pdo->exec("
    CREATE TABLE IF NOT EXISTS usuario (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL UNIQUE,
        cpf VARCHAR(14) NOT NULL UNIQUE,
        jwt TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS lotes (
        id SERIAL PRIMARY KEY,
        total_registros INTEGER NOT NULL,
        recebido_em TIMESTAMP NOT NULL DEFAULT NOW(),
        processado_em TIMESTAMP NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pendente'
    );
    
    CREATE TABLE IF NOT EXISTS fila_itens (
        id SERIAL PRIMARY KEY,
        lote_id INTEGER NOT NULL,
        indice INTEGER NOT NULL,
        payload TEXT NOT NULL,
        processado_em TIMESTAMP NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pendente',
        FOREIGN KEY (lote_id) REFERENCES lotes(id) ON DELETE CASCADE
    );
    
    CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_itens(status);
    CREATE INDEX IF NOT EXISTS idx_fila_lote ON fila_itens(lote_id);
    
    CREATE TABLE IF NOT EXISTS checkpoint_lotes (
        checkpoint_key VARCHAR(255) PRIMARY KEY,
        recebido_em TIMESTAMP NOT NULL DEFAULT NOW()
    );
");

echo "Banco de dados inicializado com sucesso!\n";
echo "Host: {$dbConfig['host']}\n";
echo "Database: {$dbConfig['database']}\n";
