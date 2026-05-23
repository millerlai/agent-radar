"""Allow ``python -m agent_radar`` as an alias for the ``agent-radar`` CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
