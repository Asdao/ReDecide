"""
Performance and latency benchmarking utilities for AI Agent learning.
"""

import time
from typing import Callable, Any, Dict, List


def measure_execution_latency(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Measure function execution latency in milliseconds."""
    start_time = time.perf_counter()
    result = fn(*args, **kwargs)
    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000.0

    return {
        "result": result,
        "latency_ms": round(latency_ms, 3),
        "is_sub_millisecond": latency_ms < 1.0,
    }


def benchmark_batch_inference(iterations: int = 100) -> Dict[str, Any]:
    """Run benchmark iterations over FastInferenceEngine telemetry lookups."""
    from src.tools.fast_cache import FastInferenceEngine

    start = time.perf_counter()
    for _ in range(iterations):
        FastInferenceEngine.lookup_zone_tactics("de_mirage", "A_SITE")
    total_time_ms = (time.perf_counter() - start) * 1000.0
    avg_latency_ms = total_time_ms / iterations

    return {
        "total_iterations": iterations,
        "total_time_ms": round(total_time_ms, 3),
        "avg_latency_ms": round(avg_latency_ms, 4),
        "throughput_ops_per_sec": int(iterations / (total_time_ms / 1000.0)),
    }
