from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import config

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Verifica o token JWT e retorna o payload decodificado.
    Levanta HTTPException se o token for inválido.
    """
    token = credentials.credentials.strip()  # Remove espaços extras do token
    
    # Verificar se JWT_SECRET não é um token JWT (erro comum)
    if config.JWT_SECRET.startswith("eyJ"):
        raise HTTPException(
            status_code=500,
            detail="Erro de configuração: JWT_SECRET não pode ser um token JWT. Use uma chave secreta."
        )
    
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token JWT ausente ou inválido: {str(e)}")
