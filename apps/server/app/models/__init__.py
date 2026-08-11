"""ORM 模型注册：Alembic autogenerate 与测试建表依赖此处导入。"""
from app.models.ai_call import AICall
from app.models.challenge import Challenge
from app.models.challenge_participant import ChallengeParticipant
from app.models.comment import Comment
from app.models.comment_like import CommentLike
from app.models.family_vote import FamilyVote
from app.models.family_vote_record import FamilyVoteRecord
from app.models.favorite import Favorite
from app.models.follow import Follow
from app.models.fridge_item import FridgeItem
from app.models.like import Like
from app.models.meal_plan import MealPlan
from app.models.my_recipe import MyRecipe
from app.models.post import Post
from app.models.qa_record import QA_Record
from app.models.recipe import Recipe
from app.models.recipe_kb import RecipeKB
from app.models.recipe_version import RecipeVersion
from app.models.shopping_list import ShoppingList
from app.models.taste_signal import TasteSignal
from app.models.user import User

__all__ = [
    "User",
    "QA_Record",
    "Recipe",
    "RecipeKB",
    "RecipeVersion",
    "Favorite",
    "AICall",
    "Post",
    "Like",
    "Comment",
    "CommentLike",
    "MealPlan",
    "MyRecipe",
    "ShoppingList",
    "TasteSignal",
    "Follow",
    "FridgeItem",
    "FamilyVote",
    "FamilyVoteRecord",
    "Challenge",
    "ChallengeParticipant",
]
