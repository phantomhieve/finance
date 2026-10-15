"""Unit and integration tests for Vault AI Gateway."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from pydantic import BaseModel

from .circuit_breaker import CircuitBreakerManager
from .gateway import AIGateway
from .registry import NodeRegistry, ProviderRegistry
from .router import NodeRouter
from .sanitizer import clean_json_text, safe_json_loads
from .types import AINode, CircuitState, TaskType


class MockTestSchema(BaseModel):
    category: str
    confidence: float
    notes: str | None = None


class SanitizerTests(SimpleTestCase):
    def test_clean_json_text_strips_think_tags(self):
        raw = "<think>Calculating risk score: 85</think>{\"category\": \"FOOD\", \"confidence\": 0.95}"
        cleaned = clean_json_text(raw)
        self.assertEqual(cleaned, '{"category": "FOOD", "confidence": 0.95}')

    def test_clean_json_text_strips_unclosed_think_tag(self):
        raw = '{"category": "RENT", "confidence": 1.0}<think>Still thinking...'
        cleaned = clean_json_text(raw)
        self.assertEqual(cleaned, '{"category": "RENT", "confidence": 1.0}')

    def test_clean_json_text_strips_fences_and_trailing_commas(self):
        raw = "```json\n{\n  \"category\": \"INVESTMENT\",\n  \"confidence\": 0.8,\n}\n```"
        cleaned = clean_json_text(raw)
        parsed = json.loads(cleaned)
        self.assertEqual(parsed["category"], "INVESTMENT")
        self.assertEqual(parsed["confidence"], 0.8)

    def test_safe_json_loads(self):
        raw = "Random text before: {\"a\": 1} random after"
        data, cleaned = safe_json_loads(raw)
        self.assertEqual(data, {"a": 1})
        self.assertEqual(cleaned, '{"a": 1}')


class CircuitBreakerTests(SimpleTestCase):
    def setUp(self):
        self.cb = CircuitBreakerManager()
        self.node = AINode(
            id="test-node-1",
            provider="openai_compatible",
            api_keys=["key-a", "key-b", "key-c"],
            default_model="llama-3",
            cooldown_seconds=10.0,
            max_retries=2,
        )

    def test_key_rotation(self):
        k1, idx1 = self.cb.get_active_key(self.node)
        k2, idx2 = self.cb.get_active_key(self.node)
        k3, idx3 = self.cb.get_active_key(self.node)
        self.assertEqual(k1, "key-a")
        self.assertEqual(k2, "key-b")
        self.assertEqual(k3, "key-c")

    def test_rate_limit_cooldown_skips_key(self):
        # Place key-a on cooldown
        self.cb.record_key_rate_limit(self.node, "key-a", cooldown_seconds=60.0)
        # Should now get key-b instead
        k, idx = self.cb.get_active_key(self.node)
        self.assertEqual(k, "key-b")

    def test_node_failure_trips_circuit(self):
        self.assertTrue(self.cb.is_node_available(self.node))
        # 1st failure
        self.cb.record_failure(self.node, RuntimeError("503 Service Unavailable"))
        self.assertTrue(self.cb.is_node_available(self.node))
        # 2nd failure hits max_retries
        self.cb.record_failure(self.node, RuntimeError("503 Service Unavailable"))
        self.assertFalse(self.cb.is_node_available(self.node))

        status = self.cb.get_status_summary()
        self.assertEqual(status["test-node-1"]["state"], CircuitState.OPEN.value)

    def test_record_success_resets_failures(self):
        self.cb.record_failure(self.node, RuntimeError("Temporary blip"))
        self.cb.record_success(self.node)
        status = self.cb.get_status_summary()
        self.assertEqual(status["test-node-1"]["consecutive_failures"], 0)


class NodeRouterTests(SimpleTestCase):
    def setUp(self):
        self.registry = NodeRegistry()
        self.cb = CircuitBreakerManager()
        self.router = NodeRouter(self.registry, self.cb)

        self.primary_node = AINode(
            id="node-pri",
            provider="openai_compatible",
            priority=1,
            api_keys=["k-pri"],
            default_model="model-pri",
        )
        self.secondary_node = AINode(
            id="node-sec",
            provider="gemini",
            priority=2,
            api_keys=["k-sec"],
            default_model="model-sec",
        )
        self.registry.register(self.primary_node)
        self.registry.register(self.secondary_node)

    def test_priority_ordering(self):
        nodes = list(self.router.plan_execution_nodes())
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0][0].id, "node-pri")
        self.assertEqual(nodes[1][0].id, "node-sec")

    def test_failover_when_primary_open(self):
        # Trip primary node circuit
        self.cb.record_failure(self.primary_node, RuntimeError("Conn Refused"))
        self.cb.record_failure(self.primary_node, RuntimeError("Conn Refused"))

        nodes = list(self.router.plan_execution_nodes())
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0][0].id, "node-sec")

    def test_explicit_preferred_node(self):
        nodes = list(self.router.plan_execution_nodes(preferred_node_id="node-sec"))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0][0].id, "node-sec")


class GatewayExecutionTests(SimpleTestCase):
    def setUp(self):
        self.gw = AIGateway()
        # Mock adapters
        self.mock_adapter_1 = MagicMock()
        self.mock_adapter_2 = MagicMock()

        ProviderRegistry.register("mock_p1", self.mock_adapter_1)
        ProviderRegistry.register("mock_p2", self.mock_adapter_2)

        self.n1 = AINode(id="n1", provider="mock_p1", priority=1, api_keys=["k1"], default_model="m1")
        self.n2 = AINode(id="n2", provider="mock_p2", priority=2, api_keys=["k2"], default_model="m2")

        self.gw.node_registry.register(self.n1)
        self.gw.node_registry.register(self.n2)
        self.gw._initialized = True

    def test_generate_text_primary_success(self):
        self.mock_adapter_1.generate_text.return_value = "Hello from N1"
        res = self.gw.generate_text("Hi", task=TaskType.FAST)
        self.assertEqual(res.content, "Hello from N1")
        self.assertEqual(res.node_id, "n1")
        self.assertFalse(res.fallback_used)

    def test_generate_text_failover_to_n2(self):
        # N1 raises exception
        self.mock_adapter_1.generate_text.side_effect = ConnectionError("Node 1 down")
        self.mock_adapter_2.generate_text.return_value = "Hello from N2 backup"

        res = self.gw.generate_text("Hi", task=TaskType.FAST)
        self.assertEqual(res.content, "Hello from N2 backup")
        self.assertEqual(res.node_id, "n2")
        self.assertTrue(res.fallback_used)

    def test_generate_structured_success(self):
        expected_obj = MockTestSchema(category="GROCERIES", confidence=0.98)
        self.mock_adapter_1.generate_structured.return_value = expected_obj

        obj = self.gw.generate_structured(MockTestSchema, "Categorize Swiggy")
        self.assertEqual(obj.category, "GROCERIES")
        self.assertEqual(obj.confidence, 0.98)


class ModelAliasNormalizationTests(SimpleTestCase):
    def test_gemini_argon_alias_normalization(self):
        from .adapters.gemini import _normalize_model_name

        self.assertEqual(_normalize_model_name("argon"), "gemini-4-argon")
        self.assertEqual(_normalize_model_name("gemini-argon"), "gemini-4-argon")
        self.assertEqual(_normalize_model_name("gemini_argon"), "gemini-4-argon")
        self.assertEqual(_normalize_model_name("ARGON"), "gemini-4-argon")
        self.assertEqual(_normalize_model_name(None), "gemini-4-argon")
        self.assertEqual(_normalize_model_name("gemini-4-argon"), "gemini-4-argon")

    def test_gemini_flash_alias_normalization(self):
        from .adapters.gemini import _normalize_model_name

        self.assertEqual(_normalize_model_name("flash"), "gemini-3.8-flash")
        self.assertEqual(_normalize_model_name("gemini-flash"), "gemini-3.8-flash")
        self.assertEqual(_normalize_model_name("3.8-flash"), "gemini-3.8-flash")
        self.assertEqual(_normalize_model_name("gemini-3.8-flash"), "gemini-3.8-flash")
        self.assertEqual(_normalize_model_name("gemini-3.5-flash-lite"), "gemini-3.8-flash")


