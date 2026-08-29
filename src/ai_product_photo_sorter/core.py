"""Public core facade over the compatibility-preserved v3.1 engine."""

from .paths import env_file, requirements_file
from . import _core_impl as _impl
from .hardening import apply_hardening
from .ollama_local import apply_ollama_local
from .dynamic_taxonomy import apply_dynamic_taxonomy
from .smart_report import apply_smart_report
from .cli_report_prompt import apply_interactive_report_prompt
from .provider_selection import apply_provider_selection
from .key_validation import apply_key_validation_hardening
from .gemini_key_resilience import apply_gemini_key_resilience
from .resource_lifecycle import apply_resource_lifecycle
from .benchmark import apply_benchmark
from .benchmark_reproducibility import apply_benchmark_reproducibility
from .hybrid_embeddings import apply_hybrid_embeddings
from .performance_pipeline import apply_performance_pipeline
from .threshold_calibration import apply_threshold_calibration
from .hybrid_routing_lab import apply_hybrid_routing_lab
from .local_evidence import apply_local_evidence
from .review_center import apply_review_center
from .sku_matching import apply_sku_matching

_impl.DEFAULT_ENV_FILE = env_file()
_impl.REQUIREMENTS_FILE = requirements_file()
apply_hardening(_impl)
apply_ollama_local(_impl)
apply_dynamic_taxonomy(_impl)
apply_smart_report(_impl)
apply_interactive_report_prompt(_impl)
apply_provider_selection(_impl)
apply_key_validation_hardening(_impl)
apply_gemini_key_resilience(_impl)
apply_resource_lifecycle(_impl)
apply_benchmark(_impl)
apply_benchmark_reproducibility(_impl)
# Shadow embeddings extend the complete benchmark/reproducibility layer.
apply_hybrid_embeddings(_impl)
# Safe preprocessing warms the final shared image cache while preserving ordered
# provider inference and operation-state mutation.
apply_performance_pipeline(_impl)
# Dataset preparation/calibration is a standalone CLI action layer.
apply_threshold_calibration(_impl)
# Routing Lab replays evidence only and never intercepts production provider calls.
apply_hybrid_routing_lab(_impl)
# Local OCR/barcode evidence never matches catalog rows or mutates grouping.
apply_local_evidence(_impl)
# Review Center human corrections mutate only review metadata and audit state.
apply_review_center(_impl)
# SKU matching is the outermost catalog layer: it consumes approved review groups,
# ranks catalog candidates, and still requires explicit human confirmation.
apply_sku_matching(_impl)

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
