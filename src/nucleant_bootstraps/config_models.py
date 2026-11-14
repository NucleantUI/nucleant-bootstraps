"""Structural view of a project's ``nucleant.toml``, as a bootstrap sees it.

The concrete model lives in NucleantProject (``nucleant.nucleant_toml``). A
bootstrap only depends on these protocols, so the two packages can move
independently as long as the shape holds.

``nucleant.toml``'s root is what ``[tool.nucleant]`` in pyproject.toml will be
later; nothing here cares which file it came from.

The ``[swift]`` table is deliberately *not* typed here. What an app's Swift side
is made of is the bootstrap's business, so each bootstrap parses it from
:attr:`NucleantTomlProtocol.data` itself (see
``bootstraps/nucleantui/swift_config.py``).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence


class AndroidServiceProtocol(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def entrypoint(self) -> str: ...

    @property
    def foreground(self) -> bool: ...

    @property
    def foreground_service_type(self) -> str | None: ...

    @property
    def start_type(self) -> str: ...

    @property
    def notification_title(self) -> str: ...

    @property
    def notification_text(self) -> str: ...

    @property
    def notification_icon(self) -> str: ...


class AndroidProtocol(Protocol):
    @property
    def package_name(self) -> str: ...

    @property
    def archs(self) -> Sequence[StrEnum]: ...

    @property
    def api(self) -> int | None: ...

    @property
    def min_api(self) -> int | None: ...

    @property
    def sdk(self) -> str | None: ...

    @property
    def ndk(self) -> str | None: ...

    @property
    def ndk_api(self) -> int | None: ...

    @property
    def icon(self) -> str | None: ...

    @property
    def presplash(self) -> str | None: ...

    @property
    def presplash_color(self) -> str | None: ...

    @property
    def presplash_lottie(self) -> str | None: ...

    @property
    def permissions(self) -> Sequence[str]: ...

    @property
    def meta_data(self) -> dict[str, str]: ...

    @property
    def gradle_dependencies(self) -> list[str]: ...

    @property
    def gradle_plugins(self) -> list[str]: ...

    @property
    def services(self) -> Sequence[AndroidServiceProtocol]: ...

    @property
    def version_code(self) -> int: ...

    @property
    def version_name(self) -> str: ...

    @property
    def include_files(self) -> Sequence[tuple[str, list[str]]]: ...

    @property
    def pre_build(self) -> Path | None: ...

    @property
    def post_build(self) -> Path | None: ...

    @property
    def byte_compile_python(self) -> bool: ...


class IosProtocol(Protocol):
    @property
    def bundle_id(self) -> str: ...

    @property
    def info_plist(self) -> dict: ...

    @property
    def entitlements(self) -> dict: ...

    @property
    def developer_team(self) -> str | None: ...

    @property
    def minimum_deployment(self) -> str | None: ...

    @property
    def version(self) -> str: ...

    @property
    def build_number(self) -> str: ...

    @property
    def pre_build(self) -> Path | None: ...

    @property
    def post_build(self) -> Path | None: ...


class MacOSProtocol(Protocol):
    @property
    def bundle_id(self) -> str: ...

    @property
    def info_plist(self) -> dict: ...

    @property
    def entitlements(self) -> dict: ...

    @property
    def developer_team(self) -> str | None: ...

    @property
    def minimum_deployment(self) -> str | None: ...

    @property
    def version(self) -> str: ...

    @property
    def build_number(self) -> str: ...

    @property
    def pre_build(self) -> Path | None: ...

    @property
    def post_build(self) -> Path | None: ...


class AppleProtocol(Protocol):
    @property
    def ios(self) -> IosProtocol | None: ...

    @property
    def macos(self) -> MacOSProtocol | None: ...


class NucleantTomlProtocol(Protocol):
    """The parts of ``nucleant.toml`` every bootstrap may read."""

    @property
    def name(self) -> str:
        """The project's module name (``my_app``)."""
        ...

    @property
    def app_name(self) -> str:
        """The display name (``MyApp``)."""
        ...

    @property
    def bootstrap(self) -> str: ...

    @property
    def android(self) -> AndroidProtocol | None: ...

    @property
    def apple(self) -> AppleProtocol | None: ...

    @property
    def python_enabled(self) -> bool:
        """Whether the (transferred, not yet enabled) Python layer is on."""
        ...

    @property
    def data(self) -> dict:
        """The raw TOML, for the sections a bootstrap parses itself."""
        ...
