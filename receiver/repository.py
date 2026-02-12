import json
from typing import Optional, Dict, Any
from database import get_db_connection
import config


class FilaRepository:
    """Repositório para gerenciar fila de lotes e itens"""

    def __init__(self, processando_timeout_minutes: int = None):
        self.processando_timeout_minutes = (
            processando_timeout_minutes or config.FILA_PROCESSANDO_TIMEOUT_MINUTES
        )

    def enfileirar_lote(
        self, total_registros: int, registros: list, checkpoint_key: Optional[str] = None
    ) -> int:
        """
        Enfileira um lote. Se checkpoint_key for informado e já existir,
        não duplica (idempotência).
        Retorna: lote_id inserido, ou 0 se já recebido (checkpoint_key duplicado)
        """
        if checkpoint_key and checkpoint_key.strip():
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM checkpoint_lotes WHERE checkpoint_key = %s",
                    (checkpoint_key,)
                )
                if cursor.fetchone():
                    return 0  # já recebido, idempotente

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                # Verificar checkpoint_key novamente dentro da transação
                if checkpoint_key and checkpoint_key.strip():
                    try:
                        cursor.execute(
                            "INSERT INTO checkpoint_lotes (checkpoint_key) VALUES (%s)",
                            (checkpoint_key,)
                        )
                    except Exception as e:
                        # Se já existe (violação de UNIQUE), retorna 0
                        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                            conn.rollback()
                            return 0
                        raise

                # Inserir lote
                cursor.execute(
                    "INSERT INTO lotes (total_registros, status) VALUES (%s, 'pendente') RETURNING id",
                    (total_registros,)
                )
                lote_id = cursor.fetchone()[0]

                # Inserir itens da fila
                cursor.executemany(
                    "INSERT INTO fila_itens (lote_id, indice, payload, status) VALUES (%s, %s, %s, 'pendente')",
                    [
                        (lote_id, i, json.dumps(reg))
                        for i, reg in enumerate(registros)
                    ]
                )
                conn.commit()
                return lote_id
            except Exception:
                conn.rollback()
                raise

    def obter_proximo_item(self) -> Optional[Dict[str, Any]]:
        """
        Devolve o próximo item pendente. Antes, recoloca como 'pendente' os itens
        que estão 'processando' há mais que FILA_PROCESSANDO_TIMEOUT_MINUTES (queda do worker).
        """
        timeout = self.processando_timeout_minutes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Recolocar itens "processando" antigos como "pendente"
            cursor.execute(f"""
                UPDATE fila_itens
                SET status = 'pendente', processado_em = NULL
                WHERE status = 'processando'
                  AND processado_em < NOW() - INTERVAL '{timeout} minutes'
            """)

            # Obter próximo item pendente (usar FOR UPDATE SKIP LOCKED para evitar bloqueios)
            cursor.execute("""
                SELECT id, lote_id, indice, payload
                FROM fila_itens
                WHERE status = 'pendente'
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
            row = cursor.fetchone()
            if not row:
                return None

            item_id, lote_id, indice, payload_json = row
            # Marcar como processando
            cursor.execute(
                "UPDATE fila_itens SET status = 'processando', processado_em = NOW() WHERE id = %s",
                (item_id,)
            )
            conn.commit()

            return {
                "id": item_id,
                "lote_id": lote_id,
                "indice": indice,
                "payload": json.loads(payload_json),
            }

    def marcar_item_processado(self, item_id: int) -> None:
        """Marca item como processado"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE fila_itens SET status = 'processado' WHERE id = %s",
                (item_id,)
            )

    def marcar_item_erro(self, item_id: int) -> None:
        """Marca item com erro"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE fila_itens SET status = 'erro' WHERE id = %s",
                (item_id,)
            )

    def estatisticas(self) -> Dict[str, int]:
        """Retorna estatísticas da fila"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM fila_itens WHERE status = 'pendente'")
            pendente = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM fila_itens WHERE status = 'processando'")
            processando = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM fila_itens WHERE status = 'processado'")
            processado = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM fila_itens WHERE status = 'erro'")
            erro = cursor.fetchone()[0]

            return {
                "pendente": pendente,
                "processando": processando,
                "processado": processado,
                "erro": erro,
                "total": pendente + processando + processado + erro,
            }
