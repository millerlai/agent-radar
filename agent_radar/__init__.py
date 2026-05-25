"""agent-radar — AI Agent capability boundary diagnostic.

See README.md for usage. Public CLI entry point: ``agent-radar``
(see :mod:`agent_radar.cli`).
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Single source of truth = pyproject.toml. Reading metadata here avoids the
# "bumped pyproject but forgot __init__" drift that hides behind --version.
try:
    __version__ = _pkg_version("claude-agent-radar")
except PackageNotFoundError:  # source checkout without install
    __version__ = "0.0.0+unknown"
