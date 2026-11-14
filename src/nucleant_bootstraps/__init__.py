"""Project generators for NucleantProject.

A bootstrap turns a project's ``nucleant.toml`` into the native projects each
platform builds from: a Gradle project for Android, an XcodeGen project for
iOS, and a SwiftPM package for the desktop ``swift run`` path.

There is one bootstrap today, ``nucleantui``. The registry in
:mod:`nucleant_bootstraps.bootstraps` exists so later app setups (other
NucleantUI modes) can sit beside it.
"""

from .bootstraps import BootstrapError, get_bootstrap, register_bootstrap

__all__ = ["BootstrapError", "get_bootstrap", "register_bootstrap"]
