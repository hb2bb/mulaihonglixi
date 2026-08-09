"""数据库会话占位：DEMO 阶段不开发数据库服务，留出扩展路径。

后续接入 SQLAlchemy 2.0 异步会话时：
- 定义 async_sessionmaker
- 提供 get_db 依赖注入
- 所有数据库操作走异步 session
"""
# 占位：DEMO 阶段不实现
