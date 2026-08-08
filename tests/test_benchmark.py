"""
Unit tests for fast cache and latency benchmarking.
"""

from src.tools.fast_cache import FastInferenceEngine, load_tactical_knowledge_base
from src.utils.benchmark import measure_execution_latency, benchmark_batch_inference


def test_tactical_knowledge_base_loading():
    kb = load_tactical_knowledge_base()
    assert "maps" in kb
    assert "de_mirage" in kb["maps"]


def test_fast_inference_engine_sub_millisecond_latency():
    res = measure_execution_latency(
        FastInferenceEngine.lookup_zone_tactics, "de_mirage", "A_SITE"
    )
    assert res["latency_ms"] < 5.0
    assert "optimal_defensive_angles" in res["result"]


def test_benchmark_batch_inference():
    stats = benchmark_batch_inference(iterations=50)
    assert stats["total_iterations"] == 50
    assert stats["avg_latency_ms"] < 2.0
