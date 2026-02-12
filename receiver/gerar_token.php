<?php
/**
 * Gera um token JWT para usar no sender (API_JWT_TOKEN) e nas chamadas à API.
 * Uso: php gerar_token.php [segundos_para_expirar]
 * Exemplo: php gerar_token.php 86400
 */
require __DIR__ . '/vendor/autoload.php';

$config = require __DIR__ . '/config.php';
$secret = $config['jwt_secret'];
$exp = (int) ($argv[1] ?? 86400); // padrão 24h

$payload = [
    'sub' => 'sender',
    'iat' => time(),
    'exp' => time() + $exp,
];

$token = \Firebase\JWT\JWT::encode($payload, $secret, 'HS256');
echo $token . "\n";
