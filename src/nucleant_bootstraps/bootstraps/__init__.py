"""Bootstrap registry.

``nucleantui`` is the main (and for now only) bootstrap. Other NucleantUI app
setups can register themselves under their own name later.
"""

from __future__ import annotations

from typing import Callable

from ..bootstrap import BootstrapProtocol, ProjectDelegate
from ..config_models import NucleantTomlProtocol

DEFAULT_BOOTSTRAP = "nucleantui"


class BootstrapError(Exception):
    pass


BootstrapFactory = Callable[[NucleantTomlProtocol, ProjectDelegate], BootstrapProtocol]

registered_bootstraps: dict[str, BootstrapFactory] = {}


def register_bootstrap(name: str, factory: BootstrapFactory) -> None:
    registered_bootstraps[name] = factory


def get_bootstrap(
    name: str, config: NucleantTomlProtocol, delegate: ProjectDelegate
) -> BootstrapProtocol:
    if name == "nucleantui":
        from .nucleantui import NucleantUIBootstrap

        return NucleantUIBootstrap(config, delegate)
    if name in registered_bootstraps:
        return registered_bootstraps[name](config, delegate)
    known = ", ".join(sorted({"nucleantui", *registered_bootstraps}))
    raise BootstrapError(f"<{name}> is not a bootstrap (known: {known})")
