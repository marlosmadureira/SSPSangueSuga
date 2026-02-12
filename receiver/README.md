# Receiver API - Python/FastAPI

API para receber lotes de dados e processar em fila. Autenticação via JWT (Bearer).

## 📋 Requisitos

- Python 3.8 ou superior
- PostgreSQL 9.5 ou superior
- pip (gerenciador de pacotes Python)

## 🚀 Instalação e Configuração

### 1. Instalar Dependências

```bash
# Navegar para o diretório receiver
cd receiver

# Instalar dependências (Python do sistema)
pip3 install -r requirements.txt
# ou: python3 -m pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar o arquivo .env com suas configurações
nano .env  # ou use seu editor preferido
```

**Configurações necessárias no `.env`:**

```env
# JWT - use o mesmo secret que gera os tokens
JWT_SECRET=seu_secret_super_seguro_aqui

# Configurações PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=sspsanguesuga
DB_USER=postgres
DB_PASSWORD=sua_senha_aqui

# Base URL da API (para documentação)
BASE_URL=http://localhost:8080

# Itens em "processando" há mais que N minutos voltam para "pendente" (queda do worker)
FILA_PROCESSANDO_TIMEOUT_MINUTES=15
```

### 3. Inicializar Banco de Dados

```bash
python3 init_db.py
```

Este script cria as seguintes tabelas:
- `lotes` - Armazena informações dos lotes recebidos
- `fila_itens` - Itens individuais da fila para processamento
- `checkpoint_lotes` - Controle de idempotência por checkpoint_key
- `usuario` - Tabela de usuários (se necessário)

### 4. Gerar Token JWT

```bash
python3 gerar_token.py
```

Copie o token gerado e use no header `Authorization: Bearer SEU_TOKEN`.

## ▶️ Executar a API

### Desenvolvimento

```bash
python3 app.py
```

Ou usando uvicorn diretamente:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

A API estará disponível em: `http://localhost:8080`

### Produção

Recomenda-se usar Gunicorn com Uvicorn workers:

```bash
# Instalar Gunicorn (se ainda não instalou)
pip3 install gunicorn

# Executar com múltiplos workers (Python do sistema)
python3 -m gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
```

**Com systemd (serviço Linux):**

Criar arquivo `/etc/systemd/system/receiver-api.service`:

```ini
[Unit]
Description=Receiver API
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/caminho/para/receiver
ExecStart=/usr/bin/python3 -m gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8080
Restart=always

[Install]
WantedBy=multi-user.target
```

Ativar e iniciar o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable receiver-api
sudo systemctl start receiver-api
sudo systemctl status receiver-api
```

## 📚 Documentação Swagger

A documentação interativa está disponível automaticamente:

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`
- **OpenAPI YAML**: `http://localhost:8080/openapi.yaml`

## 🔌 Endpoints da API

### Rotas Públicas (sem autenticação)

#### Health Check
```bash
GET /api/health
```

**Resposta:**
```json
{
  "status": "ok"
}
```

**Exemplo:**
```bash
curl http://localhost:8080/api/health
```

#### Documentação OpenAPI
```bash
GET /openapi.yaml
```

### Rotas Protegidas (requerem JWT)

Todas as rotas abaixo precisam do header:
```http
Authorization: Bearer SEU_TOKEN_JWT
```

#### 1. Enviar Lote de Registros
```bash
POST /api/lotes
```

**Body:**
```json
{
  "registros": [
    {"campo1": "valor1", "campo2": "valor2"},
    {"campo1": "valor3", "campo2": "valor4"}
  ],
  "total": 2,
  "checkpoint_key": "lote-123-unique-key"
}
```

**Resposta (sucesso):**
```json
{
  "ok": true,
  "lote_id": 1,
  "itens": 2,
  "duplicado": false
}
```

**Resposta (duplicado - idempotência):**
```json
{
  "ok": true,
  "lote_id": null,
  "itens": 2,
  "duplicado": true
}
```

**Exemplo:**
```bash
TOKEN="seu_token_jwt_aqui"
curl -X POST http://localhost:8080/api/lotes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "registros": [
      {"nome": "João", "email": "joao@example.com"},
      {"nome": "Maria", "email": "maria@example.com"}
    ],
    "checkpoint_key": "lote-2026-02-12-001"
  }'
```

**Limites:**
- Máximo de 10.000 registros por lote
- `checkpoint_key` é opcional (usado para idempotência)

#### 2. Obter Próximo Item da Fila
```bash
GET /api/fila/processar
```

**Resposta (item disponível):**
```json
{
  "item_id": 1,
  "lote_id": 1,
  "indice": 0,
  "payload": {
    "campo1": "valor1",
    "campo2": "valor2"
  }
}
```

**Resposta (fila vazia):**
```json
{
  "mensagem": "Fila vazia",
  "item": null
}
```

**Exemplo:**
```bash
curl http://localhost:8080/api/fila/processar \
  -H "Authorization: Bearer $TOKEN"
```

#### 3. Marcar Item como Processado
```bash
POST /api/fila/{id}/concluir
```

**Exemplo:**
```bash
curl -X POST http://localhost:8080/api/fila/1/concluir \
  -H "Authorization: Bearer $TOKEN"
```

#### 4. Marcar Item com Erro
```bash
POST /api/fila/{id}/erro
```

**Exemplo:**
```bash
curl -X POST http://localhost:8080/api/fila/1/erro \
  -H "Authorization: Bearer $TOKEN"
```

#### 5. Estatísticas da Fila
```bash
GET /api/fila/stats
```

**Resposta:**
```json
{
  "pendente": 10,
  "processando": 2,
  "processado": 150,
  "erro": 3,
  "total": 165
}
```

**Exemplo:**
```bash
curl http://localhost:8080/api/fila/stats \
  -H "Authorization: Bearer $TOKEN"
```

## 📝 Fluxo Completo de Uso

### 1. Enviar Lote
```bash
TOKEN="seu_token_aqui"
curl -X POST http://localhost:8080/api/lotes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "registros": [{"dado": "valor"}],
    "checkpoint_key": "lote-001"
  }'
```

### 2. Processar Itens da Fila
```bash
# Obter próximo item
RESPONSE=$(curl -s http://localhost:8080/api/fila/processar \
  -H "Authorization: Bearer $TOKEN")

# Extrair item_id (requer jq)
ITEM_ID=$(echo $RESPONSE | jq -r '.item_id')

# Processar o payload...
# ...

# Marcar como processado
curl -X POST http://localhost:8080/api/fila/$ITEM_ID/concluir \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Verificar Estatísticas
```bash
curl http://localhost:8080/api/fila/stats \
  -H "Authorization: Bearer $TOKEN"
```

## 🗄️ Estrutura do Banco de Dados

### Tabelas Criadas

**lotes**
- `id` (SERIAL PRIMARY KEY)
- `total_registros` (INTEGER)
- `recebido_em` (TIMESTAMP)
- `processado_em` (TIMESTAMP NULL)
- `status` (VARCHAR)

**fila_itens**
- `id` (SERIAL PRIMARY KEY)
- `lote_id` (INTEGER, FK para lotes)
- `indice` (INTEGER)
- `payload` (TEXT - JSON)
- `processado_em` (TIMESTAMP NULL)
- `status` (VARCHAR: pendente, processando, processado, erro)

**checkpoint_lotes**
- `checkpoint_key` (VARCHAR PRIMARY KEY)
- `recebido_em` (TIMESTAMP)

**usuario**
- `id` (SERIAL PRIMARY KEY)
- `nome` (VARCHAR)
- `email` (VARCHAR UNIQUE)
- `cpf` (VARCHAR UNIQUE)
- `jwt` (TEXT)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

## 🔒 Segurança

### Autenticação JWT
- Todas as rotas protegidas requerem token JWT válido
- Tokens são gerados com `python3 gerar_token.py`
- Tokens não expiram automaticamente (controlados pelo sistema)

### Headers de Segurança
A API adiciona automaticamente os seguintes headers:
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

### Validação de Entrada
- Validação de tipos de dados via Pydantic
- Limite de tamanho de lotes (máximo 10.000 registros)
- Validação de IDs em rotas
- Sanitização automática de entrada

### Idempotência
- Uso de `checkpoint_key` para evitar duplicação de lotes
- Se um lote com o mesmo `checkpoint_key` for enviado novamente, retorna `duplicado: true` sem criar duplicatas

## ⚙️ Configuração Avançada

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `JWT_SECRET` | Secret para assinar tokens JWT | `change-me-in-production` |
| `DB_HOST` | Host do PostgreSQL | `localhost` |
| `DB_PORT` | Porta do PostgreSQL | `5432` |
| `DB_DATABASE` | Nome do banco de dados | `sspsanguesuga` |
| `DB_USER` | Usuário do PostgreSQL | `postgres` |
| `DB_PASSWORD` | Senha do PostgreSQL | (vazio) |
| `BASE_URL` | URL base da API | `http://localhost:8080` |
| `FILA_PROCESSANDO_TIMEOUT_MINUTES` | Timeout para itens "processando" | `15` |

### Recuperação Automática de Itens Travados

Itens que ficam em status "processando" por mais que `FILA_PROCESSANDO_TIMEOUT_MINUTES` minutos são automaticamente recolocados como "pendente". Isso permite recuperação automática após queda de workers.

## 🐛 Troubleshooting

### Erro de Conexão com PostgreSQL

**Sintomas:** Erro ao inicializar ou usar a API

**Soluções:**
1. Verifique se PostgreSQL está rodando:
   ```bash
   sudo systemctl status postgresql
   ```

2. Verifique credenciais no `.env`:
   ```bash
   cat .env | grep DB_
   ```

3. Teste conexão manualmente:
   ```bash
   psql -h localhost -U postgres -d sspsanguesuga
   ```

4. Verifique se o banco foi criado:
   ```bash
   psql -h localhost -U postgres -l | grep sspsanguesuga
   ```

5. Execute `python3 init_db.py` novamente se necessário

### Token JWT Inválido

**Sintomas:** Erro 401 em rotas protegidas

**Soluções:**
1. Verifique se `JWT_SECRET` no `.env` é o mesmo usado para gerar o token
2. Certifique-se de usar `Bearer` no header:
   ```bash
   Authorization: Bearer SEU_TOKEN
   ```
3. Gere um novo token:
   ```bash
   python3 gerar_token.py
   ```

### Porta Já em Uso

**Sintomas:** Erro ao iniciar a API

**Soluções:**
1. Verifique qual processo está usando a porta:
   ```bash
   sudo lsof -i :8080
   # ou
   sudo netstat -tulpn | grep 8080
   ```

2. Altere a porta no comando ou no `app.py`:
   ```python
   uvicorn.run(app, host="0.0.0.0", port=8081)
   ```

### Erro ao Processar Lote

**Sintomas:** Erro 500 ao enviar lote

**Soluções:**
1. Verifique os logs da aplicação
2. Verifique se o banco de dados está acessível
3. Verifique se as tabelas foram criadas (`python3 init_db.py`)
4. Verifique se o lote não excede 10.000 registros

## 📦 Estrutura do Projeto

```
receiver/
├── app.py                 # Aplicação FastAPI principal
├── config.py              # Configurações do ambiente
├── models.py              # Modelos Pydantic
├── database.py            # Pool de conexões PostgreSQL
├── repository.py          # Lógica de fila
├── jwt_auth.py            # Autenticação JWT
├── init_db.py             # Script de inicialização do banco
├── gerar_token.py         # Gerador de tokens JWT
├── requirements.txt       # Dependências Python
├── .env.example           # Exemplo de configuração
├── .env                   # Configurações (não versionado)
├── openapi.yaml           # Especificação OpenAPI
└── README.md              # Este arquivo
```

## 📚 Dependências

- `fastapi` - Framework web moderno e rápido
- `uvicorn` - Servidor ASGI
- `psycopg2-binary` - Driver PostgreSQL
- `python-dotenv` - Carregamento de variáveis de ambiente
- `PyJWT` - Autenticação JWT
- `pydantic` - Validação de dados

## 🔗 Links Úteis

- [Documentação FastAPI](https://fastapi.tiangolo.com/)
- [Documentação PostgreSQL](https://www.postgresql.org/docs/)
- [Documentação JWT](https://jwt.io/)

## 📄 Licença

Este projeto é parte do sistema SSPSangueSuga.
