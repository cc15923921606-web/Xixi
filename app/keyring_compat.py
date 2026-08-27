"""Load Windows keyring without blocking on a slow platform WMI query."""
from __future__ import annotations

import importlib
import platform
import sys
from types import ModuleType


def load_keyring() -> ModuleType:
    """Import keyring while avoiding platform.system() during jaraco startup."""
    cached = sys.modules.get("keyring")
    if cached is not None:
        return cached

    # keyring also calls platform.system lazily on its first credential access
    # while selecting a backend, so restoring the function after import would
    # bring the WMI block back during application initialization.
    platform.system = lambda: "Windows"  # type: ignore[assignment]
    platform.win32_ver = lambda: ("", "", "", "")  # type: ignore[assignment]
    platform.machine = lambda: "AMD64"  # type: ignore[assignment]
    return importlib.import_module("keyring")


keyring = load_keyring()
