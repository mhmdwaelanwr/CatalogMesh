"""Public core facade over the compatibility-preserved v3.1 engine."""

from .paths import env_file, requirements_file
from . import _core_impl as _impl

_impl.DEFAULT_ENV_FILE = env_file()
_impl.REQUIREMENTS_FILE = requirements_file()

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
