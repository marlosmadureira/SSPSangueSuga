# 🔧 Solução para Erro 401 (Token JWT Inválido)

## Problema

Erro ao enviar dados do sender para o receiver:
```
401 Client Error: Unauthorized
{"detail":"Token JWT ausente ou inválido"}
```

## Causas Possíveis

1. **JWT_SECRET diferente** entre receiver e token gerado
2. **Token com espaços extras** ou quebras de linha no `.env`
3. **Token não foi copiado corretamente** do receiver para o sender

## ✅ Solução Passo a Passo

### Passo 1: Verificar JWT_SECRET no Receiver

No servidor do **receiver**, verifique o arquivo `.env`:

```bash
cd receiver
cat .env | grep JWT_SECRET
```

**Anote o valor do JWT_SECRET** (exemplo: `meu_secret_super_seguro_123`)

### Passo 2: Gerar Novo Token no Receiver

No servidor do **receiver**, gere um novo token usando o JWT_SECRET atual:

```bash
cd receiver
python3 gerar_token.py
```

**Copie o token completo** que será exibido (é uma string longa começando com `eyJ...`)

### Passo 3: Configurar Token no Sender

No servidor do **sender**, edite o arquivo `.env`:

```bash
cd sender
nano .env
```

**Configure o token** (sem aspas, sem espaços extras, tudo em uma linha):

```env
API_JWT_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZW5kZXIiLCJpYXQiOjE3MDc4OTIzNDV9.abc123def456...
```

**⚠️ IMPORTANTE:**
- Não coloque aspas ao redor do token
- Não deixe espaços antes ou depois
- Não quebre a linha (o token deve estar em uma única linha)
- Copie o token completo do receiver

### Passo 4: Testar Token

No servidor do **sender**, execute o script de teste:

```bash
cd sender
python3 testar_token.py
```

Se o teste passar, você verá:
```
✅ Token válido! Resposta: {...}
```

### Passo 5: Verificar Token no Receiver (Opcional)

Se quiser verificar se um token específico é válido no receiver:

```bash
cd receiver
python3 verificar_token.py eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 🔍 Diagnóstico Avançado

### Verificar se o Token está sendo enviado

No código do sender, o token é enviado assim:
```python
headers = {
    "Authorization": f"Bearer {API_JWT_TOKEN.strip()}",
}
```

### Verificar se o Receiver está validando corretamente

O receiver espera:
```
Authorization: Bearer <token>
```

### Verificar JWT_SECRET

Certifique-se de que o **mesmo JWT_SECRET** está sendo usado:
- No receiver: `.env` → `JWT_SECRET=...`
- Para gerar o token: `python3 gerar_token.py` usa o JWT_SECRET do `.env`

## 📝 Exemplo Completo

**Receiver (.env):**
```env
JWT_SECRET=minha_chave_secreta_123
```

**Gerar token no receiver:**
```bash
python3 gerar_token.py
# Saída: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZW5kZXIiLCJpYXQiOjE3MDc4OTIzNDV9.xyz789...
```

**Sender (.env):**
```env
API_BASE_URL=http://179.107.1.50:83/api
API_JWT_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzZW5kZXIiLCJpYXQiOjE3MDc4OTIzNDV9.xyz789...
```

## ⚠️ Erros Comuns

### Erro: Token com quebra de linha
**Sintoma:** Token parece estar correto mas ainda dá 401

**Solução:** Remova todas as quebras de linha do token no `.env`

### Erro: JWT_SECRET diferente
**Sintoma:** Token gerado não funciona

**Solução:** Use o mesmo JWT_SECRET no receiver para gerar o token e validar

### Erro: Token com espaços extras
**Sintoma:** Token parece correto mas falha

**Solução:** O código agora faz `.strip()` automaticamente, mas verifique manualmente

## 🚀 Após Corrigir

Execute o sender novamente:

```bash
cd sender
python3 sender.py
```

O erro 401 deve desaparecer e os dados devem ser enviados com sucesso!
