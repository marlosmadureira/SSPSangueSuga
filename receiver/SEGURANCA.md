# Medidas de Segurança Implementadas

Este documento descreve as medidas de segurança implementadas no receiver para proteger contra acesso não autorizado e vazamento de informações.

## Proteções Implementadas

### 1. Proteção de Arquivos Sensíveis (.htaccess)

Arquivos protegidos contra acesso direto via HTTP:
- `config.php` - Configurações do sistema
- `.env` e `.env.example` - Variáveis de ambiente
- `init_db.php` - Script de inicialização do banco
- `gerar_token.php` - Gerador de tokens JWT
- `composer.json`, `composer.lock`, `composer.phar` - Arquivos do Composer
- Arquivos de backup (`.bak`, `.backup`, `.old`, `.tmp`, `.log`, `.sql`, `.db`)
- Arquivos ocultos (começam com ponto)

### 2. Proteção de Diretórios

Diretórios bloqueados:
- `/src/` - Código fonte da aplicação
- `/data/` - Dados da aplicação (com PHP desabilitado)
- `/vendor/` - Dependências do Composer

### 3. Headers de Segurança HTTP

Headers adicionados automaticamente em todas as respostas:
- `X-Frame-Options: SAMEORIGIN` - Previne clickjacking
- `X-Content-Type-Options: nosniff` - Previne MIME type sniffing
- `X-XSS-Protection: 1; mode=block` - Proteção contra XSS
- `Referrer-Policy: strict-origin-when-cross-origin` - Controla informações de referrer
- `Content-Security-Policy` - Política de segurança de conteúdo
- Remoção de `Server` e `X-Powered-By` - Oculta informações do servidor

### 4. Tratamento de Erros Seguro

- Erros não expõem informações sensíveis (stack traces, caminhos de arquivos, etc.)
- Mensagens genéricas para o cliente
- Logs detalhados apenas no servidor (via `error_log()`)

### 5. Validação de Entrada

- Validação de tipos de dados
- Limite de tamanho de lotes (máximo 10.000 registros)
- Validação de IDs em rotas
- Sanitização de entrada

### 6. Autenticação JWT

- Todas as rotas da API (exceto `/api/health` e `/openapi.yaml`) requerem autenticação JWT
- Tokens sem expiração (controlados pela tabela `usuario`)

## Configuração Recomendada

### Permissões de Arquivos

```bash
# Arquivos PHP devem ser executáveis apenas pelo servidor web
chmod 644 *.php
chmod 644 config.php

# Arquivos de configuração devem ser protegidos
chmod 600 .env

# Diretórios devem ter permissões restritas
chmod 755 src/
chmod 700 data/
```

### Configuração do Servidor Web

1. **Desabilitar listagem de diretórios** (já implementado via `.htaccess`)
2. **Desabilitar execução de PHP em diretórios de dados** (já implementado)
3. **Usar HTTPS em produção** (configurar no servidor web)
4. **Configurar firewall** para permitir apenas portas necessárias
5. **Manter PHP atualizado** com as últimas correções de segurança

### Variáveis de Ambiente

Nunca commitar o arquivo `.env` no controle de versão. Use apenas `.env.example` como template.

## Checklist de Segurança

- [x] Arquivos sensíveis protegidos via `.htaccess`
- [x] Diretórios protegidos contra acesso direto
- [x] Headers de segurança HTTP configurados
- [x] Tratamento de erros sem expor informações sensíveis
- [x] Validação de entrada implementada
- [x] Autenticação JWT em rotas protegidas
- [ ] HTTPS configurado (configurar no servidor)
- [ ] Firewall configurado (configurar no servidor)
- [ ] Logs de segurança monitorados (implementar conforme necessário)
- [ ] Backup regular do banco de dados (implementar conforme necessário)

## Notas Importantes

1. **Tokens JWT**: Os tokens não expiram automaticamente. Para revogar acesso:
   - Alterar `JWT_SECRET` no `.env` (invalida todos os tokens)
   - Implementar controle de usuários ativos/inativos na tabela `usuario`

2. **Banco de Dados**: As credenciais do PostgreSQL estão no `.env`. Certifique-se de que este arquivo não seja acessível via web.

3. **Logs**: Erros são registrados via `error_log()`. Configure o PHP para escrever logs em local seguro e não acessível via web.

4. **Produção**: Em ambiente de produção, considere:
   - Desabilitar `display_errors` no PHP
   - Configurar `error_reporting` apropriadamente
   - Implementar rate limiting
   - Configurar monitoramento de segurança
