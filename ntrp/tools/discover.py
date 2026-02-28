import importlib.util
import sys
from pathlib import Path

from ntrp.config import NTRP_DIR
from ntrp.logging import get_logger
from ntrp.tools.core.base import Tool

_logger = get_logger(__name__)

USER_TOOLS_DIR = NTRP_DIR / "tools"


def discover_user_tools(tools_dir: Path = USER_TOOLS_DIR) -> list[type[Tool]]:
    if not tools_dir.is_dir():
        return []

    tools: list[type[Tool]] = []

    for path in sorted(tools_dir.glob("*.py")):
        try:
            module_name = f"ntrp_user_tools.{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Tool) and attr is not Tool:
                    tools.append(attr)

        except Exception:
            _logger.warning("Failed to load user tool from %s", path.name, exc_info=True)

    return tools
