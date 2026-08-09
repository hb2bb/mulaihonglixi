"""加密工具占位：DEMO 阶段不实现，后续接入用户鉴权时补全。"""
# TODO: 后续接入用户密码哈希、token 生成与校验时实现


def hash_password(plain: str) -> str:
    """占位：密码哈希。"""
    raise NotImplementedError("encrypt 模块尚未实现，DEMO 阶段不需要")


def verify_password(plain: str, hashed: str) -> bool:
    """占位：密码校验。"""
    raise NotImplementedError("encrypt 模块尚未实现，DEMO 阶段不需要")
