<?php
/**
 * Gera um token JWT para usar no sender (API_JWT_TOKEN) e nas chamadas à API.
 * O token não expira e pode ser usado enquanto o usuário estiver ativo no sistema.
 * Uso: php gerar_token.php
 */
require __DIR__ . '/vendor/autoload.php';

$config = require __DIR__ . '/config.php';
$secret = $config['jwt_secret'];

$payload = [
    'sub' => 'sender',
    'iat' => time(),
    // Sem campo 'exp' - token não expira
];

$token = \Firebase\JWT\JWT::encode($payload, $secret, 'HS256');
echo $token . "\n";
