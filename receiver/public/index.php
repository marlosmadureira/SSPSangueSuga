<?php
use Receiver\FilaRepository;
use Receiver\JwtMiddleware;
use Slim\Factory\AppFactory;
use Slim\Middleware\BodyParsingMiddleware;
use Slim\Routing\RouteCollectorProxy;

require __DIR__ . '/../vendor/autoload.php';

$config = require __DIR__ . '/../config.php';
$app = AppFactory::create();
$app->add(new BodyParsingMiddleware());
$app->addErrorMiddleware(true, true, true);

$jwt = new JwtMiddleware($config['jwt_secret']);
$fila = new FilaRepository(
    $config['fila_db'],
    $config['fila_processando_timeout_minutes'] ?? 15
);

// Rotas públicas (sem JWT)
$app->get('/api/health', function ($req, $res) {
    $res->getBody()->write(json_encode(['status' => 'ok']));
    return $res->withHeader('Content-Type', 'application/json');
});

$app->get('/openapi.yaml', function ($req, $res) use ($config) {
    $yaml = file_get_contents(__DIR__ . '/../openapi.yaml');
    $yaml = str_replace('{{BASE_URL}}', $config['base_url'], $yaml);
    $res->getBody()->write($yaml);
    return $res->withHeader('Content-Type', 'application/x-yaml');
});

// Grupo protegido por JWT
$app->group('/api', function (RouteCollectorProxy $group) use ($fila) {
    $group->post('/lotes', function ($req, $res) use ($fila) {
        $body = $req->getParsedBody() ?? [];
        $registros = $body['registros'] ?? [];
        $total = (int) ($body['total'] ?? count($registros));
        $checkpointKey = $body['checkpoint_key'] ?? null;
        if (empty($registros)) {
            $res->getBody()->write(json_encode(['erro' => 'Nenhum registro no lote']));
            return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
        }
        $loteId = $fila->enfileirarLote($total, $registros, $checkpointKey);
        $duplicado = ($loteId === 0 && $checkpointKey !== null);
        $res->getBody()->write(json_encode([
            'ok' => true,
            'lote_id' => $duplicado ? null : $loteId,
            'itens' => count($registros),
            'duplicado' => $duplicado,
        ]));
        return $res->withHeader('Content-Type', 'application/json');
    });

    $group->get('/fila/processar', function ($req, $res) use ($fila) {
        $item = $fila->obterProximoItem();
        if (!$item) {
            $res->getBody()->write(json_encode(['mensagem' => 'Fila vazia', 'item' => null]));
            return $res->withHeader('Content-Type', 'application/json');
        }
        $res->getBody()->write(json_encode([
            'item_id' => $item['id'],
            'lote_id' => $item['lote_id'],
            'indice' => $item['indice'],
            'payload' => $item['payload'],
        ]));
        return $res->withHeader('Content-Type', 'application/json');
    });

    $group->post('/fila/{id}/concluir', function ($req, $res, $args) use ($fila) {
        $id = (int) $args['id'];
        $fila->marcarItemProcessado($id);
        $res->getBody()->write(json_encode(['ok' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    });

    $group->post('/fila/{id}/erro', function ($req, $res, $args) use ($fila) {
        $id = (int) $args['id'];
        $fila->marcarItemErro($id);
        $res->getBody()->write(json_encode(['ok' => true]));
        return $res->withHeader('Content-Type', 'application/json');
    });

    $group->get('/fila/stats', function ($req, $res) use ($fila) {
        $res->getBody()->write(json_encode($fila->estatisticas()));
        return $res->withHeader('Content-Type', 'application/json');
    });
})->add($jwt);

$app->run();
