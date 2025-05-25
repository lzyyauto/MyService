from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from fastapi.security import HTTPBearer as HTTPBearerSecurity
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User


# 自定义 HTTPBearer 以添加 swagger 文档
class HTTPBearer(HTTPBearerSecurity):

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        self.scheme_name = "Bearer"
        self.description = "输入格式: Bearer <your-token>"


security = HTTPBearer()


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Security(security),
        db: Session = Depends(get_db)) -> User:
    """
    从 Authorization header 中获取并验证 token
    格式: Authorization: Bearer <token>
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user = db.query(User).filter(User.api_key == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# 为了向后兼容，保留旧函数但使用新的实现
async def verify_token(current_user: User = Depends(get_current_user)) -> User:
    return current_user
