"""ABAC (Attribute-Based Access Control) service package"""
from .engine import ABACEngine, get_abac_engine
from .context import AccessContext, AccessContextBuilder
from .evaluator import PolicyEvaluator

__all__ = [
    "ABACEngine",
    "get_abac_engine",
    "AccessContext",
    "AccessContextBuilder",
    "PolicyEvaluator",
]
