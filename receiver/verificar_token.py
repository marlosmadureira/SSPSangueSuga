#!/usr/bin/env python3
"""
Script para verificar se o token JWT pode ser decodificado com o JWT_SECRET atual.
Uso: python3 verificar_token.py <token>
"""
import jwt
import sys
import config

if len(sys.argv) < 2:
    print("Uso: python3 verificar_token.py <token_jwt>")
    print()
    print("Exemplo:")
    print("  python3 verificar_token.py eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    sys.exit(1)

token = sys.argv[1].strip()

print("=" * 60)
print("VERIFICAÇÃO DE TOKEN JWT")
print("=" * 60)
print()
print(f"JWT_SECRET configurado: {config.JWT_SECRET[:20]}...{config.JWT_SECRET[-10:]}")
print(f"Tamanho do secret: {len(config.JWT_SECRET)} caracteres")
print()
print(f"Token recebido: {token[:30]}...{token[-30:]}")
print(f"Tamanho do token: {len(token)} caracteres")
print()

try:
    payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    print("✅ Token válido!")
    print(f"   Payload: {payload}")
except jwt.ExpiredSignatureError:
    print("❌ Token expirado")
except jwt.InvalidTokenError as e:
    print(f"❌ Token inválido: {e}")
    print()
    print("POSSÍVEIS CAUSAS:")
    print("1. O token foi gerado com um JWT_SECRET diferente")
    print("2. O JWT_SECRET no receiver não corresponde ao usado para gerar o token")
    print()
    print("SOLUÇÃO:")
    print("1. Verifique o JWT_SECRET no arquivo .env do receiver")
    print("2. Gere um novo token com: python3 gerar_token.py")
    print("3. Use o mesmo JWT_SECRET no receiver e no token gerado")
    sys.exit(1)
