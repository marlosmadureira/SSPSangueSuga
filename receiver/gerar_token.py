#!/usr/bin/env python3
"""
Gera um token JWT para usar no sender (API_JWT_TOKEN) e nas chamadas à API.
O token não expira e pode ser usado enquanto o usuário estiver ativo no sistema.
Uso: python gerar_token.py
"""
import jwt
import time
import sys
import config

# Verificar se JWT_SECRET está configurado corretamente
if not config.JWT_SECRET or config.JWT_SECRET == "change-me-in-production":
    print("❌ ERRO: JWT_SECRET não está configurado!", file=sys.stderr)
    print("   Configure JWT_SECRET no arquivo .env com uma chave secreta forte.", file=sys.stderr)
    sys.exit(1)

# Verificar se JWT_SECRET parece ser um token JWT (erro comum)
if config.JWT_SECRET.startswith("eyJ"):
    print("❌ ERRO: JWT_SECRET parece ser um token JWT, não uma chave secreta!", file=sys.stderr)
    print("   O JWT_SECRET deve ser uma chave secreta aleatória (ex: uma senha forte)", file=sys.stderr)
    print("   NÃO deve ser um token JWT (que começa com 'eyJ')", file=sys.stderr)
    sys.exit(1)

payload = {
    "sub": "sender",
    "iat": int(time.time()),
    # Sem campo 'exp' - token não expira
}

token = jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
print(token)
