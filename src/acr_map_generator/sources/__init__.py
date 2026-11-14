"""Data sources, one subpackage per data kind. Importing this package registers all providers.

To add a provider: create sources/<kind>/<id>.py with a class exposing `info`, `covers()` and
`fetch()` (see core.registry.Provider), call `register(...)` at module level, and import the
module in sources/<kind>/__init__.py. Import order there is auto-selection priority.
"""

from . import roads, terrain  # noqa: F401
