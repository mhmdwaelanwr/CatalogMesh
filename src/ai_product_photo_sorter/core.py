"""Public core facade over the compatibility-preserved v3.1 engine."""

from .paths import env_file, requirements_file
from . import _core_impl as _impl
from .hardening import apply_hardening
from .dynamic_taxonomy import apply_dynamic_taxonomy
from .smart_report import apply_smart_report
from .cli_report_prompt import apply_interactive_report_prompt
from .benchmark import apply_benchmark

_impl.DEFAULT_ENV_FILE = env_file()
_impl.REQUIREMENTS_FILE = requirements_file()
apply_hardening(_impl)
apply_dynamic_taxonomy(_impl)
apply_smart_report(_impl)
apply_interactive_report_prompt(_impl)
apply_benchmark(_impl)

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
