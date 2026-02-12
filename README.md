# dumSSP – Envio e recebimento em lote

Dois projetos: **sender** (envio a partir do SQL Server em lotes de 1000) e **receiver** (API PHP que recebe em fila com JWT e Swagger).

---

## 1. Sender (Python) – Envio

Lê uma tabela do SQL Server e envia os dados em lotes de 1000 para a API do receiver.

### Requisitos

- Python 3.8+
- ODBC Driver for SQL Server (ex.: [ODBC Driver 17](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server))

### Instalação

```bash
cd sender
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edite .env com: DB_*, API_BASE_URL, API_JWT_TOKEN
```

### Configuração (.env)

| Variável         | Descrição |
|------------------|-----------|
| DB_SERVER        | Servidor SQL Server |
| DB_NAME          | Nome do banco |
| DB_USER / DB_PASSWORD | Credenciais |
| DB_DRIVER        | Ex.: `ODBC Driver 17 for SQL Server` |
| DB_TABLE         | Nome da tabela a exportar |
| DB_ORDER_COLUMN  | (Opcional) Coluna para ordenar (ex.: `id`) |
| API_BASE_URL     | URL base da API do receiver (ex.: `http://localhost:8080/api`) |
| API_JWT_TOKEN    | Token JWT válido (o mesmo secret do receiver) |
| BATCH_SIZE       | Tamanho do lote (padrão 1000) |
| STATE_FILE       | Arquivo de checkpoint para retomar (padrão: `.sender_state.json`) |
| RETRY_ATTEMPTS   | Tentativas em caso de queda de conexão (padrão: 5) |
| RETRY_BACKOFF_SECONDS | Segundos entre tentativas (padrão: 5) |

### Retomada após queda (envio)

- O sender grava um **checkpoint** após cada lote enviado com sucesso (arquivo `.sender_state.json`).
- Se houver queda de energia ou de conexão, **execute de novo** `python sender.py`: ele retoma de onde parou.
- Se houver `DB_ORDER_COLUMN`, a retomada usa **paginação por chave** (mais estável). Caso contrário, usa offset.
- Em falha de rede, o envio **tenta de novo** algumas vezes antes de desistir; ao desistir, o checkpoint não é avançado, então na próxima execução o mesmo lote é reenviado. O receiver evita duplicar lotes graças ao `checkpoint_key`.

### Uso

```bash
python sender.py
```

---

## 2. Receiver (PHP) – Recebimento em fila

API que recebe lotes via `POST /api/lotes` (com JWT), enfileira e permite processar item a item.

### Requisitos

- PHP 7.4+
- Composer
- Servidor web (Apache com mod_rewrite ou PHP built-in)

### Instalação

```bash
cd receiver
composer install
cp .env.example .env
# Defina JWT_SECRET (mesmo usado para gerar o token que o sender envia)
php init_db.php
```

Se você já tinha o receiver instalado antes da funcionalidade de retomada, rode de novo `php init_db.php` para criar a tabela `checkpoint_lotes`.

### Configuração (.env)

| Variável      | Descrição |
|---------------|-----------|
| JWT_SECRET    | Secret para validar o JWT (gerar token com o mesmo secret) |
| FILA_DB_PATH  | Caminho do SQLite da fila (padrão: `data/fila.db`) |
| BASE_URL      | URL base da API (para o Swagger) |
| FILA_PROCESSANDO_TIMEOUT_MINUTES | Minutos após os quais itens "processando" voltam para "pendente" (queda do worker; padrão: 15) |

### Subir o servidor (desenvolvimento)

```bash
cd receiver/public
php -S 0.0.0.0:8080
```

Documentação Swagger (YAML): `GET http://localhost:8080/openapi.yaml`  
Você pode importar no Swagger UI ou no PHP que você já usa.

### Endpoints (todos os `/api/*` exigem JWT)

- **POST /api/lotes** – Recebe um lote (`registros`, opcional `total`, opcional `checkpoint_key`). Se `checkpoint_key` já existir, não duplica (idempotente).
- **GET /api/fila/processar** – Retorna o próximo item da fila. Itens travados em "processando" por mais que X minutos voltam a "pendente" (retomada após queda do worker).
- **POST /api/fila/{id}/concluir** – Marca o item como processado.
- **POST /api/fila/{id}/erro** – Marca o item com erro.
- **GET /api/fila/stats** – Estatísticas (pendente, processado, erro, total).

Header em todas as chamadas protegidas:

```http
Authorization: Bearer SEU_TOKEN_JWT
```

### Retomada após queda (recebimento)

- Os dados recebidos ficam no **SQLite**; em queda de energia do servidor, nada se perde.
- Se o **worker** (quem chama `/api/fila/processar`) cair sem chamar concluir/erro, os itens ficam "processando". Após **FILA_PROCESSANDO_TIMEOUT_MINUTES**, eles voltam para "pendente" e podem ser processados de novo.
- O sender envia `checkpoint_key` por lote; se o mesmo lote for reenviado (retry após queda), o receiver **não duplica** (idempotência).

### Fluxo de processamento

1. Sender envia lotes para `POST /api/lotes` com o JWT (e `checkpoint_key` para idempotência).
2. Receiver grava cada lote na fila (SQLite).
3. Seu processo (worker) chama `GET /api/fila/processar` (com JWT), processa o `payload` e depois:
   - `POST /api/fila/{item_id}/concluir` em sucesso
   - `POST /api/fila/{item_id}/erro` em falha

### Gerar um token JWT para testes

No diretório **receiver**:

```bash
php gerar_token.php        # token válido por 24h
php gerar_token.php 3600   # token válido por 1h
```

Use o mesmo **JWT_SECRET** no `.env` do receiver. Copie o token gerado para `API_JWT_TOKEN` no `.env` do sender.

---

## Resumo

| Projeto   | Função |
|----------|--------|
| **sender**  | Lê tabela no SQL Server → envia lotes de 1000 para a API (JWT). |
| **receiver**| API PHP: recebe lotes (JWT), enfileira; você consome com `GET /api/fila/processar` e marca concluído/erro. |

Swagger: servir `receiver/public` e acessar `/openapi.yaml` para importar na sua estrutura Swagger em PHP.
