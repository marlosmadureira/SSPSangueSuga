<?php
namespace Receiver;

use Firebase\JWT\JWT;
use Firebase\JWT\Key;
use Psr\Http\Message\ServerRequestInterface as Request;
use Psr\Http\Server\RequestHandlerInterface as RequestHandler;
use Slim\Psr7\Response;

class JwtMiddleware
{
    private string $secret;

    public function __construct(string $secret)
    {
        $this->secret = $secret;
    }

    public function __invoke(Request $request, RequestHandler $handler): Response
    {
        $auth = $request->getHeaderLine('Authorization');
        if (!preg_match('/^Bearer\s+(.+)$/i', $auth, $m)) {
            $response = new Response();
            $response->getBody()->write(json_encode(['erro' => 'Token JWT ausente ou inválido']));
            return $response->withStatus(401)->withHeader('Content-Type', 'application/json');
        }
        $token = trim($m[1]);
        try {
            $decoded = JWT::decode($token, new Key($this->secret, 'HS256'));
            $request = $request->withAttribute('jwt', $decoded);
            return $handler->handle($request);
        } catch (\Throwable $e) {
            $response = new Response();
            $response->getBody()->write(json_encode(['erro' => 'Token inválido ou expirado']));
            return $response->withStatus(401)->withHeader('Content-Type', 'application/json');
        }
    }
}
