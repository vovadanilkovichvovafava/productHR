"""
Tests for Entity AI prompts - verify humor/sarcasm handling instructions.

These tests ensure the AI prompts include proper instructions for:
- Distinguishing humor from real red flags
- Understanding sarcasm and informal communication
- Not flagging jokes as problems
"""
import pytest
import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.services.entity_ai import ENTITY_QUICK_ACTIONS, EntityAIService


class TestEntityAIPrompts:
    """Tests for AI prompt content."""

    def test_full_analysis_includes_humor_instruction(self):
        """Verify full_analysis prompt mentions humor/sarcasm."""
        prompt = ENTITY_QUICK_ACTIONS["full_analysis"]

        # Should mention not to confuse jokes with red flags
        assert "юмор" in prompt.lower() or "шутки" in prompt.lower()
        assert "red flag" in prompt.lower() or "red flags" in prompt.lower()

    def test_red_flags_excludes_humor(self):
        """Verify red_flags prompt explicitly excludes humor."""
        prompt = ENTITY_QUICK_ACTIONS["red_flags"]

        # Should have section about what NOT to consider as red flags
        assert "НЕ считай red flags" in prompt or "не red flag" in prompt.lower()

        # Should mention humor, sarcasm, slang
        assert "юмор" in prompt.lower()
        assert "сарказм" in prompt.lower()
        assert "сленг" in prompt.lower()

        # Should mention emojis
        assert "эмодзи" in prompt.lower()

    def test_red_flags_mentions_context(self):
        """Verify red_flags prompt asks to distinguish context."""
        prompt = ENTITY_QUICK_ACTIONS["red_flags"]

        # Should mention context awareness
        assert "контекст" in prompt.lower()

    def test_system_prompt_includes_humor_rules(self):
        """Verify system prompt includes humor understanding rules."""
        service = EntityAIService()

        # Build system prompt with empty context
        system_prompt = service._build_system_prompt("Test context")

        # Should have rule about distinguishing humor
        assert "юмор" in system_prompt.lower() or "сарказм" in system_prompt.lower()

        # Should mention informal communication is normal
        assert "неформальный" in system_prompt.lower() or "коммуникаци" in system_prompt.lower()

    def test_system_prompt_has_9_rules(self):
        """Verify system prompt has all 9 rules including new ones."""
        service = EntityAIService()
        system_prompt = service._build_system_prompt("Test context")

        # Count numbered rules
        import re
        rules = re.findall(r'\d+\.', system_prompt)

        # Should have at least 9 rules (including the new humor ones)
        assert len(rules) >= 9


class TestEntityAIQuickActions:
    """Tests for quick action prompts structure."""

    def test_all_quick_actions_exist(self):
        """Verify all required quick actions are defined."""
        required_actions = [
            "full_analysis",
            "red_flags",
            "comparison",
            "prediction",
            "summary",
            "questions"
        ]

        for action in required_actions:
            assert action in ENTITY_QUICK_ACTIONS, f"Missing action: {action}"

    def test_quick_actions_are_non_empty(self):
        """Verify all quick action prompts have content."""
        for action, prompt in ENTITY_QUICK_ACTIONS.items():
            assert len(prompt) > 100, f"Action {action} prompt too short"

    def test_quick_actions_in_russian(self):
        """Verify prompts are in Russian."""
        for action, prompt in ENTITY_QUICK_ACTIONS.items():
            # Russian text should contain Cyrillic characters
            cyrillic_count = sum(1 for c in prompt if '\u0400' <= c <= '\u04FF')
            assert cyrillic_count > 20, f"Action {action} should be in Russian"


class TestEntityAIService:
    """Tests for EntityAIService class."""

    def test_service_initialization(self):
        """Verify service initializes correctly."""
        service = EntityAIService()

        assert service._client is None  # Lazy initialization
        assert service.model == "claude-sonnet-4-6"

    def test_get_available_actions(self):
        """Verify get_available_actions returns all actions."""
        service = EntityAIService()
        actions = service.get_available_actions()

        assert len(actions) == 6
        action_ids = [a["id"] for a in actions]

        assert "full_analysis" in action_ids
        assert "red_flags" in action_ids
        assert "summary" in action_ids
