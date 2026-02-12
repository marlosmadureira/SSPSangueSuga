# dumSSP – Envio e recebimento em lote

Sistema composto por dois componentes: **sender** (envio a partir do SQL Server em lotes de 1000) e **receiver** (API Python/FastAPI que recebe em fila com JWT e Swagger).

---

## 📋 Visão Geral da Arquitetura

```
┌─────────────────┐         HTTP/HTTPS + JWT        ┌─────────────────┐
│                 │                                 │                 │
│   MÁQUINA 1     │                                 │   MÁQUINA 2     │
│                 │                                 │                 │
│   SENDER        │ ──────────────────────────────> │   RECEIVER      │
│   (Python)      │                                 │   (Python/      │
│                 │                                 │    FastAPI)     │
│   SQL Server    │                                 │   PostgreSQL    │
│   (origem)      │                                 │   (destino)     │
└─────────────────┘                                 └─────────────────┘
```

**Fluxo:**
1. Sender lê dados do SQL Server em lotes de 1000 registros
2. Sender envia lotes para o Receiver via API REST (com JWT)
3. Receiver enfileira os dados no PostgreSQL
4. Worker processa itens da fila um a um

---

## 🚀 Instalação Passo a Passo

### Cenário: Instalação em Máquinas Separadas

Este guia assume que você instalará:
- **Receiver** na **Máquina 1** (servidor de destino)
- **Sender** na **Máquina 2** (servidor de origem/SQL Server)

---

## 📦 PARTE 1: Instalação do RECEIVER (Máquina 1)

### Pré-requisitos da Máquina 1

- Sistema operacional: Linux (Ubuntu/Debian recomendado) ou Windows
- Python 3.8 ou superior
- PostgreSQL 9.5 ou superior
- Acesso root/sudo (para instalar PostgreSQL se necessário)
- Porta 8080 disponível (ou outra porta de sua escolha)

### Passo 1.1: Instalar PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Criar banco de dados:**
```bash
sudo -u postgres psql
```

No prompt do PostgreSQL:
```sql
CREATE DATABASE sspsanguesuga;
CREATE USER seu_usuario WITH PASSWORD 'sua_senha_segura';
GRANT ALL PRIVILEGES ON DATABASE sspsanguesuga TO seu_usuario;
\q
```

### Passo 1.2: Instalar Python e Dependências

**Ubuntu/Debian:**
```bash
sudo apt install -y python3 python3-pip python3-venv
```

**Windows:**
- Baixe Python 3.8+ de [python.org](https://www.python.org/downloads/)
- Marque a opção "Add Python to PATH" durante a instalação

### Passo 1.3: Preparar Diretório do Receiver

```bash
# Criar diretório para o projeto
mkdir -p /opt/receiver
cd /opt/receiver

# Copiar arquivos do receiver para este diretório
# (copie toda a pasta receiver/ do projeto)
```

### Passo 1.4: Configurar Ambiente Virtual

```bash
cd /opt/receiver

# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### Passo 1.5: Instalar Dependências Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Passo 1.6: Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar o arquivo .env
nano .env  # ou use seu editor preferido
```

**Configurar o `.env` do Receiver:**

```env
# JWT - use um secret forte e único
JWT_SECRET=seu_secret_super_seguro_aqui_mude_este_valor

# Configurações PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=sspsanguesuga
DB_USER=seu_usuario
DB_PASSWORD=sua_senha_segura

# Base URL da API (use o IP ou domínio da Máquina 1)
BASE_URL=http://IP_DA_MAQUINA_1:8080
# Exemplo: BASE_URL=http://192.168.1.100:8080
# Ou em produção: BASE_URL=https://api.seudominio.com

# Itens em "processando" há mais que N minutos voltam para "pendente"
FILA_PROCESSANDO_TIMEOUT_MINUTES=15
```

**⚠️ IMPORTANTE:** Anote o valor de `JWT_SECRET` - você precisará dele na Máquina 2!

### Passo 1.7: Inicializar Banco de Dados

```bash
python init_db.py
```

Você deve ver a mensagem: "Banco de dados inicializado com sucesso!"

### Passo 1.8: Gerar Token JWT

```bash
python gerar_token.py
```

**⚠️ IMPORTANTE:** Copie o token gerado - você precisará dele na Máquina 2 para configurar o sender!

**Exemplo de saída:**
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZW5kZXIiLCJpYXQiOjE3MDc4OTIzNDV9.abc123def456...
```

### Passo 1.9: Testar Receiver Localmente

```bash
# Executar em modo desenvolvimento
python app.py
```

Ou usando uvicorn diretamente:
```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

**Testar se está funcionando:**

Em outro terminal:
```bash
# Health check
curl http://localhost:8080/api/health

# Deve retornar: {"status":"ok"}
```

### Passo 1.10: Configurar Firewall (se necessário)

**Ubuntu/Debian (UFW):**
```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

**CentOS/RHEL (firewalld):**
```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### Passo 1.11: Configurar como Serviço (Produção)

**Criar arquivo de serviço systemd:**

```bash
sudo nano /etc/systemd/system/receiver-api.service
```

**Conteúdo do arquivo:**

```ini
[Unit]
Description=Receiver API
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/receiver
Environment="PATH=/opt/receiver/venv/bin"
ExecStart=/opt/receiver/venv/bin/gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Ativar e iniciar o serviço:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable receiver-api
sudo systemctl start receiver-api
sudo systemctl status receiver-api
```

**Verificar logs:**
```bash
sudo journalctl -u receiver-api -f
```

### Passo 1.12: Verificar IP da Máquina 1

```bash
# Linux
hostname -I
# ou
ip addr show

# Windows
ipconfig
```

**⚠️ IMPORTANTE:** Anote o IP da Máquina 1 - você precisará dele na Máquina 2!

---

## 📤 PARTE 2: Instalação do SENDER (Máquina 2)

### Pré-requisitos da Máquina 2

- Sistema operacional: Linux ou Windows
- Python 3.8 ou superior
- Acesso ao SQL Server (origem dos dados)
- Conectividade de rede com a Máquina 1 (porta 8080)
- ODBC Driver for SQL Server instalado (se necessário)

### Passo 2.1: Instalar Python

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

**Windows:**
- Baixe Python 3.8+ de [python.org](https://www.python.org/downloads/)

### Passo 2.2: Instalar Driver SQL Server (Linux)

**Ubuntu/Debian:**
```bash
# Instalar dependências
sudo apt install -y unixodbc-dev gcc

# Instalar pymssql (driver Python para SQL Server)
pip3 install pymssql
```

**Windows:**
- O driver já está incluído ou pode ser instalado via pip

### Passo 2.3: Preparar Diretório do Sender

```bash
# Criar diretório para o projeto
mkdir -p /opt/sender
cd /opt/sender

# Copiar arquivos do sender para este diretório
# (copie toda a pasta sender/ do projeto)
```

### Passo 2.4: Configurar Ambiente Virtual

```bash
cd /opt/sender

# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### Passo 2.5: Instalar Dependências Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Passo 2.6: Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar o arquivo .env
nano .env  # ou use seu editor preferido
```

**Configurar o `.env` do Sender:**

```env
# SQL Server (origem)
DB_SERVER=IP_DO_SQL_SERVER
DB_PORT=1433
DB_NAME=nome_do_banco
DB_USER=usuario_sql_server
DB_PASSWORD=senha_sql_server
DB_TIMEOUT=30
DB_LOGIN_TIMEOUT=10

# Tabela a ser exportada (suporta schema.tabela, ex: SchEventos.Usuario)
DB_TABLE=SchEventos.Usuario
# Opcional: coluna para ordenar (ex. id) - recomendado para melhor performance
DB_ORDER_COLUMN=id

# API de destino (Máquina 1 - Receiver)
API_BASE_URL=http://IP_DA_MAQUINA_1:8080/api
# Exemplo: API_BASE_URL=http://192.168.1.100:8080/api
# Ou em produção: API_BASE_URL=https://api.seudominio.com/api

# Token JWT gerado na Máquina 1 (copie o token gerado no Passo 1.8)
API_JWT_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZW5kZXIiLCJpYXQiOjE3MDc4OTIzNDV9.abc123def456...

# Tamanho do lote
BATCH_SIZE=1000

# Arquivo de estado para retomar após queda (caminho absoluto ou relativo)
STATE_FILE=.sender_state.json

# Retry em caso de queda de conexão
RETRY_ATTEMPTS=5
RETRY_BACKOFF_SECONDS=5
```

**⚠️ IMPORTANTE:** 
- Substitua `IP_DA_MAQUINA_1` pelo IP real da Máquina 1 (anotado no Passo 1.12)
- Substitua `API_JWT_TOKEN` pelo token gerado na Máquina 1 (Passo 1.8)
- Configure corretamente as credenciais do SQL Server

### Passo 2.7: Testar Conexão com SQL Server

```bash
# Testar se consegue conectar ao SQL Server
python3 -c "
import pymssql
conn = pymssql.connect(
    server='IP_DO_SQL_SERVER',
    port=1433,
    database='nome_do_banco',
    user='usuario_sql_server',
    password='senha_sql_server'
)
print('✅ Conexão com SQL Server OK!')
conn.close()
"
```

### Passo 2.8: Testar Conexão com Receiver

```bash
# Testar se consegue acessar o Receiver
curl http://IP_DA_MAQUINA_1:8080/api/health

# Deve retornar: {"status":"ok"}
```

**Se não funcionar, verifique:**
- Firewall da Máquina 1 permite conexões na porta 8080
- Receiver está rodando na Máquina 1
- IP está correto

### Passo 2.9: Testar Envio (Dry Run)

Antes de executar o sender completo, você pode testar com um lote pequeno:

```bash
# Executar o sender
python sender.py
```

O sender irá:
1. Conectar ao SQL Server
2. Ler os primeiros 1000 registros (ou conforme BATCH_SIZE)
3. Enviar para o Receiver
4. Salvar checkpoint em `.sender_state.json`

**Verificar se funcionou:**

Na Máquina 1, verificar estatísticas:
```bash
curl http://IP_DA_MAQUINA_1:8080/api/fila/stats \
  -H "Authorization: Bearer SEU_TOKEN_JWT"
```

### Passo 2.10: Configurar como Serviço (Produção)

**Criar arquivo de serviço systemd:**

```bash
sudo nano /etc/systemd/system/sender.service
```

**Conteúdo do arquivo:**

```ini
[Unit]
Description=Sender - Envio de dados para Receiver
After=network.target

[Service]
Type=simple
User=seu_usuario
Group=seu_grupo
WorkingDirectory=/opt/sender
Environment="PATH=/opt/sender/venv/bin"
ExecStart=/opt/sender/venv/bin/python sender.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Ativar e iniciar o serviço:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable sender
sudo systemctl start sender
sudo systemctl status sender
```

**Verificar logs:**
```bash
sudo journalctl -u sender -f
```

---

## ✅ Verificação Final

### Testar Comunicação Entre Máquinas

**Na Máquina 2 (Sender):**
```bash
# Testar acesso ao Receiver
curl http://IP_DA_MAQUINA_1:8080/api/health

# Testar autenticação JWT
curl http://IP_DA_MAQUINA_1:8080/api/fila/stats \
  -H "Authorization: Bearer SEU_TOKEN_JWT"
```

**Na Máquina 1 (Receiver):**
```bash
# Verificar se está rodando
sudo systemctl status receiver-api

# Ver logs
sudo journalctl -u receiver-api -n 50
```

### Executar Envio Completo

**Na Máquina 2:**
```bash
cd /opt/sender
source venv/bin/activate
python sender.py
```

O sender irá:
- Ler todos os registros da tabela em lotes de 1000
- Enviar cada lote para o Receiver
- Salvar checkpoint após cada lote
- Retomar automaticamente se houver queda

**Monitorar progresso:**

Na Máquina 1, acompanhar estatísticas:
```bash
watch -n 5 'curl -s http://localhost:8080/api/fila/stats -H "Authorization: Bearer SEU_TOKEN_JWT" | jq'
```

---

## 🔧 Troubleshooting

### Problema: Sender não consegue conectar ao Receiver

**Sintomas:** Erro de conexão ao tentar enviar dados

**Soluções:**
1. Verificar se Receiver está rodando:
   ```bash
   # Na Máquina 1
   sudo systemctl status receiver-api
   ```

2. Verificar firewall:
   ```bash
   # Na Máquina 1
   sudo ufw status
   sudo ufw allow 8080/tcp
   ```

3. Testar conectividade:
   ```bash
   # Na Máquina 2
   telnet IP_DA_MAQUINA_1 8080
   # ou
   nc -zv IP_DA_MAQUINA_1 8080
   ```

4. Verificar IP e porta no `.env` do sender

### Problema: Erro 401 (Token inválido)

**Sintomas:** Receiver retorna erro 401 ao receber lotes

**Soluções:**
1. Verificar se `JWT_SECRET` no Receiver é o mesmo usado para gerar o token
2. Regenerar token na Máquina 1:
   ```bash
   python gerar_token.py
   ```
3. Atualizar `API_JWT_TOKEN` no `.env` do Sender

### Problema: Erro de conexão com SQL Server

**Sintomas:** Sender não consegue ler dados do SQL Server

**Soluções:**
1. Verificar credenciais no `.env`
2. Testar conexão manualmente (Passo 2.7)
3. Verificar se SQL Server permite conexões remotas
4. Verificar firewall do SQL Server

### Problema: Receiver não inicia

**Sintomas:** Erro ao iniciar o serviço receiver-api

**Soluções:**
1. Verificar logs:
   ```bash
   sudo journalctl -u receiver-api -n 100
   ```

2. Verificar se PostgreSQL está rodando:
   ```bash
   sudo systemctl status postgresql
   ```

3. Verificar configurações no `.env`
4. Testar manualmente:
   ```bash
   cd /opt/receiver
   source venv/bin/activate
   python app.py
   ```

---

## 📊 Monitoramento

### Ver Estatísticas da Fila

```bash
curl http://IP_DA_MAQUINA_1:8080/api/fila/stats \
  -H "Authorization: Bearer SEU_TOKEN_JWT"
```

### Ver Logs do Receiver

```bash
sudo journalctl -u receiver-api -f
```

### Ver Logs do Sender

```bash
sudo journalctl -u sender -f
```

### Verificar Checkpoint do Sender

```bash
cat /opt/sender/.sender_state.json
```

---

## 🔄 Retomada Após Queda

### Sender

O sender salva checkpoint após cada lote. Se houver queda:
1. Execute novamente: `python sender.py`
2. Ele retomará automaticamente de onde parou

### Receiver

Os dados ficam no PostgreSQL. Se houver queda:
1. Reinicie o serviço: `sudo systemctl restart receiver-api`
2. Os dados permanecem intactos no banco

### Worker (Processamento da Fila)

Itens que ficam "processando" por mais de 15 minutos (configurável) voltam automaticamente para "pendente" e podem ser processados novamente.

---

## 📝 Resumo das Configurações

### Máquina 1 (Receiver)

| Item | Valor |
|------|-------|
| IP | `IP_DA_MAQUINA_1` |
| Porta | `8080` |
| Banco | PostgreSQL (`sspsanguesuga`) |
| JWT_SECRET | `seu_secret_super_seguro` |
| Token JWT | Gerado com `python gerar_token.py` |

### Máquina 2 (Sender)

| Item | Valor |
|------|-------|
| SQL Server | `IP_DO_SQL_SERVER:1433` |
| Banco Origem | `nome_do_banco` |
| Tabela | `SchEventos.Usuario` |
| API Destino | `http://IP_DA_MAQUINA_1:8080/api` |
| Token JWT | Copiado da Máquina 1 |

---

## 🔗 Documentação Adicional

- **Receiver**: Veja `receiver/README.md` para detalhes completos da API
- **Sender**: Veja código fonte em `sender/sender.py` para lógica de envio
- **Swagger**: Acesse `http://IP_DA_MAQUINA_1:8080/docs` para documentação interativa

---

## 📞 Suporte

Em caso de problemas:
1. Verifique os logs de ambos os serviços
2. Teste conectividade de rede entre as máquinas
3. Verifique configurações no `.env` de ambos os componentes
4. Consulte a seção de Troubleshooting acima
