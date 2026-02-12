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
    token = credentials.credentials
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token JWT ausente ou inválido")
