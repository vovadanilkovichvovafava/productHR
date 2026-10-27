"""Policy evaluator for ABAC"""
from typing import Any, Dict, List, Optional, Tuple
import logging

from ...models.abac import (
    ABACPolicy, ABACPolicyCondition,
    PolicyEffect, AttributeType, ConditionOperator, AccessDecision
)
from .context import AccessContext

logger = logging.getLogger(__name__)


class PolicyEvaluator:
    """Evaluates ABAC policies against access context"""

    def evaluate(
        self,
        policies: List[ABACPolicy],
        context: AccessContext
    ) -> Tuple[AccessDecision, Optional[ABACPolicy]]:
        """
        Evaluate policies and return access decision.

        Policies are evaluated in priority order (highest first).
        First matching policy determines the result.
        If no policy matches, default is DENY.

        Returns:
            Tuple of (decision, matched_policy)
        """
        # Sort by priority descending
        sorted_policies = sorted(policies, key=lambda p: (p.priority, -p.id), reverse=True)

        for policy in sorted_policies:
            if not policy.is_active:
                continue

            if self._policy_matches(policy, context):
                decision = (
                    AccessDecision.allow
                    if policy.effect == PolicyEffect.allow
                    else AccessDecision.deny
                )
                logger.debug(
                    f"Policy '{policy.name}' matched - {decision.value}",
                    extra={"policy_id": policy.id, "context": context.to_dict()}
                )
                return decision, policy

        # No policy matched - default deny
        logger.debug("No policy matched - default deny")
        return AccessDecision.deny, None

    def _policy_matches(self, policy: ABACPolicy, context: AccessContext) -> bool:
        """Check if all policy conditions match the context"""
        if not policy.conditions:
            # Policy with no conditions always matches (like default_deny)
            return True

        for condition in policy.conditions:
            if not self._condition_matches(condition, context):
                return False

        return True

    def _condition_matches(
        self, condition: ABACPolicyCondition, context: AccessContext
    ) -> bool:
        """Check if a single condition matches"""
        attr_value = context.get(
            condition.attribute_type.value,
            condition.attribute_name
        )

        operator = condition.operator
        expected = condition.value

        return self._evaluate_operator(operator, attr_value, expected)

    def _evaluate_operator(
        self,
        operator: ConditionOperator,
        actual: Any,
        expected: Any
    ) -> bool:
        """Evaluate a condition operator"""
        try:
            if operator == ConditionOperator.eq:
                return actual == expected

            elif operator == ConditionOperator.neq:
                return actual != expected

            elif operator == ConditionOperator.in_:
                if isinstance(expected, list):
                    return actual in expected
                return False

            elif operator == ConditionOperator.not_in:
                if isinstance(expected, list):
                    return actual not in expected
                return True

            elif operator == ConditionOperator.gt:
                return actual is not None and actual > expected

            elif operator == ConditionOperator.lt:
                return actual is not None and actual < expected

            elif operator == ConditionOperator.gte:
                return actual is not None and actual >= expected

            elif operator == ConditionOperator.lte:
                return actual is not None and actual <= expected

            elif operator == ConditionOperator.contains:
                if isinstance(actual, (list, str)):
                    return expected in actual
                return False

            elif operator == ConditionOperator.not_contains:
                if isinstance(actual, (list, str)):
                    return expected not in actual
                return True

            elif operator == ConditionOperator.is_null:
                return actual is None

            elif operator == ConditionOperator.is_not_null:
                return actual is not None

            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except Exception as e:
            logger.warning(
                f"Error evaluating condition: {operator} on {actual} vs {expected}: {e}"
            )
            return False


class PolicyEvaluatorWithCache:
    """Policy evaluator with condition result caching for batch operations"""

    def __init__(self):
        self._base_evaluator = PolicyEvaluator()
        self._condition_cache: Dict[str, bool] = {}

    def evaluate_batch(
        self,
        policies: List[ABACPolicy],
        contexts: List[AccessContext]
    ) -> List[Tuple[AccessDecision, Optional[ABACPolicy]]]:
        """Evaluate policies for multiple contexts efficiently"""
        results = []

        for context in contexts:
            result = self._base_evaluator.evaluate(policies, context)
            results.append(result)

        return results

    def clear_cache(self):
        """Clear condition cache"""
        self._condition_cache.clear()
