"""自定义业务异常体系 + 全局统一响应封装。

所有接口返回统一结构 {code, msg, data}；
业务异常继承 BizException，由全局异常处理器捕获并格式化返回。
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    """统一响应结构体。"""

    model_config = ConfigDict(from_attributes=True)

    code: int
    msg: str
    data: Optional[Any] = None


def success_resp(data: Any = None, msg: str = "ok") -> ApiResponse:
    """构造成功响应。"""
    return ApiResponse(code=0, msg=msg, data=data)


def fail_resp(code: int, msg: str, data: Any = None) -> ApiResponse:
    """构造失败响应。"""
    return ApiResponse(code=code, msg=msg, data=data)


class BizException(Exception):
    """业务异常基类，子类通过 code 区分业务错误码。"""

    def __init__(self, code: int, msg: str, data: Any = None) -> None:
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(msg)


class ValidationError(BizException):
    """入参校验失败。"""

    def __init__(self, msg: str = "参数校验失败", data: Any = None) -> None:
        super().__init__(code=4001, msg=msg, data=data)


class SessionError(BizException):
    """session_id 非法或格式错误。"""

    def __init__(self, msg: str = "session 非法", data: Any = None) -> None:
        super().__init__(code=4002, msg=msg, data=data)


class ResourceNotFoundError(BizException):
    """请求资源不存在。"""

    def __init__(self, msg: str = "资源不存在", data: Any = None) -> None:
        super().__init__(code=4004, msg=msg, data=data)


class LLMCallError(BizException):
    """LLM 调用失败。"""

    def __init__(self, msg: str = "LLM 调用失败", data: Any = None) -> None:
        super().__init__(code=5001, msg=msg, data=data)


class HistoryPersistError(BizException):
    """聊天历史持久化失败。"""

    def __init__(self, msg: str = "历史记录写入失败", data: Any = None) -> None:
        super().__init__(code=5002, msg=msg, data=data)


__all__ = [
    "ApiResponse",
    "success_resp",
    "fail_resp",
    "BizException",
    "ValidationError",
    "SessionError",
    "ResourceNotFoundError",
    "LLMCallError",
    "HistoryPersistError",
]
