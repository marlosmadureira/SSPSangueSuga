#!/usr/bin/env python3
"""
Gera um token JWT para usar no sender (API_JWT_TOKEN) e nas chamadas à API.
O token não expira e pode ser usado enquanto o usuário estiver ativo no sistema.
Uso: python gerar_token.py
"""
import jwt
import time
import config

payload = {
    "sub": "sender",
    "iat": int(time.time()),
    # Sem campo 'exp' - token não expira
}

token = jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
print(token)
