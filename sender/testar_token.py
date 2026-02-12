#!/usr/bin/env python3
"""
Script para testar se o token JWT está configurado corretamente.
Uso: python3 testar_token.py
"""
import requests
import sys
from config import API_BASE_URL, API_JWT_TOKEN

def testar_token():
    print("=" * 60)
    print("TESTE DE TOKEN JWT")
    print("=" * 60)
    print()
    
    # Verificar se token está configurado
    if not API_JWT_TOKEN:
        print("❌ ERRO: API_JWT_TOKEN não está configurado no .env")
        print("   Configure API_JWT_TOKEN no arquivo .env do sender")
        return 1
    
    if not API_JWT_TOKEN.strip():
        print("❌ ERRO: API_JWT_TOKEN está vazio (apenas espaços)")
        return 1
    
    print(f"✅ Token encontrado: {API_JWT_TOKEN[:20]}...{API_JWT_TOKEN[-20:]}")
    print(f"   Tamanho: {len(API_JWT_TOKEN)} caracteres")
    print()
    
    # Verificar URL
    if not API_BASE_URL:
        print("❌ ERRO: API_BASE_URL não está configurado no .env")
        return 1
    
    print(f"✅ URL configurada: {API_BASE_URL}")
    print()
    
    # Testar health check (sem token)
    print("1. Testando health check (sem token)...")
    try:
        base = API_BASE_URL.rsplit("/api", 1)[0] if "/api" in API_BASE_URL else API_BASE_URL.rstrip("/api")
        health_url = f"{base}/api/health"
        r = requests.get(health_url, timeout=5)
        if r.status_code == 200:
            print(f"   ✅ Health check OK: {r.json()}")
        else:
            print(f"   ⚠️  Health check retornou: {r.status_code}")
    except Exception as e:
        print(f"   ❌ Erro ao conectar: {e}")
        return 1
    
    print()
    
    # Testar endpoint protegido (com token)
    print("2. Testando endpoint protegido (com token)...")
    try:
        url = f"{API_BASE_URL.rstrip('/')}/fila/stats"
        headers = {
            "Authorization": f"Bearer {API_JWT_TOKEN.strip()}",
            "Content-Type": "application/json",
        }
        print(f"   URL: {url}")
        print(f"   Header Authorization: Bearer {API_JWT_TOKEN[:30]}...")
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            print(f"   ✅ Token válido! Resposta: {r.json()}")
            return 0
        elif r.status_code == 401:
            print(f"   ❌ Token inválido ou rejeitado (401)")
            print(f"   Resposta: {r.text}")
            print()
            print("   POSSÍVEIS CAUSAS:")
            print("   1. O token foi gerado com um JWT_SECRET diferente do receiver")
            print("   2. O token tem espaços extras ou quebras de linha")
            print("   3. O JWT_SECRET no receiver não corresponde ao usado para gerar o token")
            print()
            print("   SOLUÇÃO:")
            print("   1. No receiver, execute: python3 gerar_token.py")
            print("   2. Copie o token gerado")
            print("   3. No sender, edite .env e configure: API_JWT_TOKEN=<token_copiado>")
            print("   4. Certifique-se de que JWT_SECRET no receiver é o mesmo usado para gerar o token")
            return 1
        else:
            print(f"   ⚠️  Status inesperado: {r.status_code}")
            print(f"   Resposta: {r.text}")
            return 1
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Erro de conexão: não foi possível conectar ao receiver")
        print(f"   Verifique se o receiver está rodando em {API_BASE_URL}")
        return 1
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(testar_token())
