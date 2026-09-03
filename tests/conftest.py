"""Keep the suite hermetic against a developer's local configuration.

`Settings` reads `.env` so a deployment can be configured by file. Following
the local-stack guide in `docs/development.md` creates exactly that file, and
from then on it also feeds every test that constructs `Settings` without
naming a field: `meo_base_url` silently becomes the local Meo, no `respx` mock
matches, and most of the suite fails with errors that point nowhere near the
cause. Tests supply their own configuration and must ignore the file.
"""

from meo_mcp.config import Settings

Settings.model_config["env_file"] = None
