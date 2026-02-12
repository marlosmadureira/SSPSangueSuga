<?php
use Receiver\FilaRepository;
use Receiver\JwtMiddleware;
use Slim\Factory\AppFactory;
use Slim\Middleware\BodyParsingMiddleware;
use Slim\Routing\RouteCollectorProxy;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

require __DIR__ . '/../vendor/autoload.php';

$config = require __DIR__ . '/../config.php';
$app = AppFactory::create();
$app->add(new BodyParsingMiddleware());

// Middleware de segurança - tratamento de erros sem expor informações sensíveis
$errorMiddleware = $app->addErrorMiddleware(false, false, false);
$errorHandler = $errorMiddleware->getDefaultErrorHandler();
$errorHandler->forceContentType('application/json');
$errorHandler->registerErrorRenderer('application/json', function () {
    return new class {
        public function __invoke($request, $exception, $displayErrorDetails, $logErrors, $logErrorDetails): Response {
            $response = new \Slim\Psr7\Response();
            $response->getBody()->write(json_encode([
                'erro' => 'Erro interno do servidor'
            ]));
            return $response->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    };
});

$jwt = new JwtMiddleware($config['jwt_secret']);
$fila = new FilaRepository(
    $config['db'],
    $config['fila_processando_timeout_minutes'] ?? 15
);

// Middleware para adicionar headers de segurança em todas as respostas
$app->add(function (Request $request, $handler): Response {
    $response = $handler->handle($request);
    return $response
        ->withHeader('X-Frame-Options', 'SAMEORIGIN')
        ->withHeader('X-Content-Type-Options', 'nosniff')
        ->withHeader('X-XSS-Protection', '1; mode=block')
        ->withHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
});

// Rotas públicas (sem JWT)
$app->get('/api/health', function (Request $req, Response $res) {
    $res->getBody()->write(json_encode(['status' => 'ok']));
    return $res->withHeader('Content-Type', 'application/json');
});

$app->get('/openapi.yaml', function (Request $req, Response $res) use ($config) {
    $yamlPath = __DIR__ . '/../openapi.yaml';
    if (!file_exists($yamlPath)) {
        $res->getBody()->write(json_encode(['erro' => 'Arquivo não encontrado']));
        return $res->withStatus(404)->withHeader('Content-Type', 'application/json');
    }
    $yaml = file_get_contents($yamlPath);
    $yaml = str_replace('{{BASE_URL}}', $config['base_url'], $yaml);
    $res->getBody()->write($yaml);
    return $res->withHeader('Content-Type', 'application/x-yaml');
});

// Grupo protegido por JWT
$app->group('/api', function (RouteCollectorProxy $group) use ($fila) {
    $group->post('/lotes', function (Request $req, Response $res) use ($fila) {
        try {
            $body = $req->getParsedBody() ?? [];
            $registros = $body['registros'] ?? [];
            $total = (int) ($body['total'] ?? count($registros));
            $checkpointKey = $body['checkpoint_key'] ?? null;
            
            // Validação de entrada
            if (empty($registros) || !is_array($registros)) {
                $res->getBody()->write(json_encode(['erro' => 'Nenhum registro no lote']));
                return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
            }
            
            // Limitar tamanho do lote
            if (count($registros) > 10000) {
                $res->getBody()->write(json_encode(['erro' => 'Lote muito grande. Máximo 10000 registros']));
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
        } catch (\Throwable $e) {
            error_log('Erro ao processar lote: ' . $e->getMessage());
            $res->getBody()->write(json_encode(['erro' => 'Erro ao processar lote']));
            return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    });

    $group->get('/fila/processar', function (Request $req, Response $res) use ($fila) {
        try {
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
        } catch (\Throwable $e) {
            error_log('Erro ao obter próximo item: ' . $e->getMessage());
            $res->getBody()->write(json_encode(['erro' => 'Erro ao processar fila']));
            return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    });

    $group->post('/fila/{id}/concluir', function (Request $req, Response $res, array $args) use ($fila) {
        try {
            $id = (int) ($args['id'] ?? 0);
            if ($id <= 0) {
                $res->getBody()->write(json_encode(['erro' => 'ID inválido']));
                return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
            }
            $fila->marcarItemProcessado($id);
            $res->getBody()->write(json_encode(['ok' => true]));
            return $res->withHeader('Content-Type', 'application/json');
        } catch (\Throwable $e) {
            error_log('Erro ao marcar item como processado: ' . $e->getMessage());
            $res->getBody()->write(json_encode(['erro' => 'Erro ao processar']));
            return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    });

    $group->post('/fila/{id}/erro', function (Request $req, Response $res, array $args) use ($fila) {
        try {
            $id = (int) ($args['id'] ?? 0);
            if ($id <= 0) {
                $res->getBody()->write(json_encode(['erro' => 'ID inválido']));
                return $res->withStatus(400)->withHeader('Content-Type', 'application/json');
            }
            $fila->marcarItemErro($id);
            $res->getBody()->write(json_encode(['ok' => true]));
            return $res->withHeader('Content-Type', 'application/json');
        } catch (\Throwable $e) {
            error_log('Erro ao marcar item com erro: ' . $e->getMessage());
            $res->getBody()->write(json_encode(['erro' => 'Erro ao processar']));
            return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    });

    $group->get('/fila/stats', function (Request $req, Response $res) use ($fila) {
        try {
            $res->getBody()->write(json_encode($fila->estatisticas()));
            return $res->withHeader('Content-Type', 'application/json');
        } catch (\Throwable $e) {
            error_log('Erro ao obter estatísticas: ' . $e->getMessage());
            $res->getBody()->write(json_encode(['erro' => 'Erro ao obter estatísticas']));
            return $res->withStatus(500)->withHeader('Content-Type', 'application/json');
        }
    });
})->add($jwt);

$app->run();
