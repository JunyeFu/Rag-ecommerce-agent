"""ORM 模型包 — 自动建表依赖导入"""
from app.models.product import Product
from app.models.session import Session
from app.models.message import Message
from app.models.feedback import Feedback
from app.models.knowledge import KnowledgeVersion
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.cart import CartItem
from app.models.order import Order
from app.models.favorite import Favorite
from app.models.footprint import Footprint
from app.models.user import User
from app.models.review import Review

__all__ = [
    "Product", "Session", "Message", "Feedback", "KnowledgeVersion",
    "KnowledgeChunk", "CartItem", "Order", "Favorite", "Footprint", "User", "Review",
]
