<?php
/**
 * Cria as tabelas da fila. Execute uma vez: php init_db.php
 */
$config = require __DIR__ . '/config.php';
$dir = dirname($config['fila_db']);
if (!is_dir($dir)) {
    mkdir($dir, 0755, true);
}
$pdo = new PDO('sqlite:' . $config['fila_db']);
$pdo->exec("
    CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_registros INTEGER NOT NULL,
        recebido_em TEXT NOT NULL DEFAULT (datetime('now')),
        processado_em TEXT NULL,
        status TEXT NOT NULL DEFAULT 'pendente'
    );
    CREATE TABLE IF NOT EXISTS fila_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lote_id INTEGER NOT NULL,
        indice INTEGER NOT NULL,
        payload TEXT NOT NULL,
        processado_em TEXT NULL,
        status TEXT NOT NULL DEFAULT 'pendente',
        FOREIGN KEY (lote_id) REFERENCES lotes(id)
    );
    CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_itens(status);
    CREATE INDEX IF NOT EXISTS idx_fila_lote ON fila_itens(lote_id);
    CREATE TABLE IF NOT EXISTS checkpoint_lotes (
        checkpoint_key TEXT PRIMARY KEY,
        recebido_em TEXT NOT NULL DEFAULT (datetime('now'))
    );
");
echo "Banco da fila inicializado: " . $config['fila_db'] . "\n";
