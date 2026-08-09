"""ORM 模型注册：Alembic autogenerate 与测试建表依赖此处导入。"""
from app.models.ai_call import AICall
from app.models.favorite import Favorite
from app.models.like import Like
from app.models.post import Post
from app.models.qa_record import QA_Record
from app.models.recipe import Recipe
from app.models.user import User

__all__ = ["User", "QA_Record", "Recipe", "Favorite", "AICall", "Post", "Like"]
