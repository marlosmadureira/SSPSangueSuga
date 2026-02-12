<?php
$envPath = __DIR__ . '/.env';
if (is_file($envPath)) {
    foreach (file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        if (strpos($line, '=') !== false && strpos(trim($line), '#') !== 0) {
            [$name, $value] = explode('=', $line, 2);
            $_ENV[trim($name)] = trim($value, " \t\"'");
        }
    }
}
return [
    'jwt_secret' => $_ENV['JWT_SECRET'] ?? 'change-me-in-production',
    'fila_db'    => $_ENV['FILA_DB_PATH'] ?? __DIR__ . '/data/fila.db',
    'base_url'   => $_ENV['BASE_URL'] ?? 'http://localhost:8080',
    'fila_processando_timeout_minutes' => (int) ($_ENV['FILA_PROCESSANDO_TIMEOUT_MINUTES'] ?? 15),
];
