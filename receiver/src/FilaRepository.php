<?php
namespace Receiver;

use PDO;

class FilaRepository
{
    private PDO $pdo;
    private int $processandoTimeoutMinutes;

    public function __construct(string $dbPath, int $processandoTimeoutMinutes = 15)
    {
        $this->processandoTimeoutMinutes = $processandoTimeoutMinutes;
        $dir = dirname($dbPath);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        $this->pdo = new PDO('sqlite:' . $dbPath);
        $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    }

    /**
     * Enfileira um lote. Se checkpoint_key for informado e já existir, não duplica (idempotência).
     * @return int lote_id inserido, ou 0 se já recebido (checkpoint_key duplicado)
     */
    public function enfileirarLote(int $totalRegistros, array $registros, ?string $checkpointKey = null): int
    {
        if ($checkpointKey !== null && $checkpointKey !== '') {
            $exists = $this->pdo->prepare("SELECT 1 FROM checkpoint_lotes WHERE checkpoint_key = ?");
            $exists->execute([$checkpointKey]);
            if ($exists->fetchColumn()) {
                return 0; // já recebido, idempotente
            }
        }

        $this->pdo->beginTransaction();
        try {
            if ($checkpointKey !== null && $checkpointKey !== '') {
                try {
                    $this->pdo->prepare("INSERT INTO checkpoint_lotes (checkpoint_key) VALUES (?)")
                        ->execute([$checkpointKey]);
                } catch (\PDOException $e) {
                    if ((int) $e->getCode() === 23000 || strpos($e->getMessage(), 'UNIQUE') !== false) {
                        $this->pdo->rollBack();
                        return 0; // já recebido (idempotente)
                    }
                    throw $e;
                }
            }

            $stmt = $this->pdo->prepare("INSERT INTO lotes (total_registros, status) VALUES (?, 'pendente')");
            $stmt->execute([$totalRegistros]);
            $loteId = (int) $this->pdo->lastInsertId();

            $stmt = $this->pdo->prepare("INSERT INTO fila_itens (lote_id, indice, payload, status) VALUES (?, ?, ?, 'pendente')");
            foreach ($registros as $i => $reg) {
                $stmt->execute([$loteId, $i, json_encode($reg)]);
            }
            $this->pdo->commit();
            return $loteId;
        } catch (\Throwable $e) {
            $this->pdo->rollBack();
            throw $e;
        }
    }

    /**
     * Devolve o próximo item pendente. Antes, recoloca como 'pendente' os itens
     * que estão 'processando' há mais que FILA_PROCESSANDO_TIMEOUT_MINUTES (queda do worker).
     */
    public function obterProximoItem(): ?array
    {
        $timeout = $this->processandoTimeoutMinutes;
        $this->pdo->exec("
            UPDATE fila_itens
            SET status = 'pendente', processado_em = NULL
            WHERE status = 'processando'
              AND processado_em < datetime('now', '-{$timeout} minutes')
        ");

        $this->pdo->beginTransaction();
        $row = $this->pdo->query("
            SELECT id, lote_id, indice, payload
            FROM fila_itens
            WHERE status = 'pendente'
            ORDER BY id ASC
            LIMIT 1
        ")->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            $this->pdo->commit();
            return null;
        }
        $this->pdo->prepare("UPDATE fila_itens SET status = 'processando', processado_em = datetime('now') WHERE id = ?")
            ->execute([$row['id']]);
        $this->pdo->commit();
        $row['payload'] = json_decode($row['payload'], true);
        return $row;
    }

    public function marcarItemProcessado(int $id): void
    {
        $this->pdo->prepare("UPDATE fila_itens SET status = 'processado' WHERE id = ?")->execute([$id]);
    }

    public function marcarItemErro(int $id): void
    {
        $this->pdo->prepare("UPDATE fila_itens SET status = 'erro' WHERE id = ?")->execute([$id]);
    }

    public function estatisticas(): array
    {
        $pendente = $this->pdo->query("SELECT COUNT(*) FROM fila_itens WHERE status = 'pendente'")->fetchColumn();
        $processando = $this->pdo->query("SELECT COUNT(*) FROM fila_itens WHERE status = 'processando'")->fetchColumn();
        $processado = $this->pdo->query("SELECT COUNT(*) FROM fila_itens WHERE status = 'processado'")->fetchColumn();
        $erro = $this->pdo->query("SELECT COUNT(*) FROM fila_itens WHERE status = 'erro'")->fetchColumn();
        return [
            'pendente' => (int) $pendente,
            'processando' => (int) $processando,
            'processado' => (int) $processado,
            'erro' => (int) $erro,
            'total' => (int) $pendente + (int) $processando + (int) $processado + (int) $erro,
        ];
    }
}
