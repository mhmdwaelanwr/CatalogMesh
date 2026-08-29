"""Public core facade over the compatibility-preserved v3.1 engine."""

from .paths import env_file, requirements_file
from . import _core_impl as _impl
from .hardening import apply_hardening
from .dynamic_taxonomy import apply_dynamic_taxonomy
from .smart_report import apply_smart_report
from .cli_report_prompt import apply_interactive_report_prompt
from .provider_selection import apply_provider_selection
from .key_validation import apply_key_validation_hardening
from .gemini_key_resilience import apply_gemini_key_resilience
from .resource_lifecycle import apply_resource_lifecycle
from .benchmark import apply_benchmark
from .benchmark_reproducibility import apply_benchmark_reproducibility

_impl.DEFAULT_ENV_FILE = env_file()
_impl.REQUIREMENTS_FILE = requirements_file()
apply_hardening(_impl)
apply_dynamic_taxonomy(_impl)
apply_smart_report(_impl)
apply_interactive_report_prompt(_impl)
apply_provider_selection(_impl)
apply_key_validation_hardening(_impl)
apply_gemini_key_resilience(_impl)
apply_resource_lifecycle(_impl)
apply_benchmark(_impl)
apply_benchmark_reproducibility(_impl)

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
