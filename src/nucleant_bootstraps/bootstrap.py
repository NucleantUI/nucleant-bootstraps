"""What a bootstrap is handed by NucleantProject, and what it offers back.

A *delegate* is the CLI's side: where the project is, which toolchain was
resolved, and how to run the tools the CLI owns (xcodegen, CPython installs).
A bootstrap never resolves a toolchain itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class ProjectDelegate(Protocol):
    @property
    def working_dir(self) -> Path: ...

    @property
    def swift_executable(self) -> str:
        """Absolute path of the pinned ``swift`` (or ``"swift"`` from PATH)."""
        ...

    @property
    def swift_env(self) -> dict[str, str]:
        """Extra environment every Swift invocation of this project gets."""
        ...


@runtime_checkable
class GradleProjectDelegate(Protocol):
    @property
    def working_dir(self) -> Path: ...

    @property
    def swift_executable(self) -> str: ...

    @property
    def swift_env(self) -> dict[str, str]: ...

    @property
    def swift_android_sdk(self) -> str | None:
        """The installed Swift SDK id to build with (``swift-6.3.3-RELEASE_android``)."""
        ...

    @property
    def default_api_version(self) -> int: ...

    @property
    def sdk_path(self) -> str: ...

    @property
    def ndk_version(self) -> str: ...

    @property
    def ndk_path(self) -> str: ...

    @property
    def java_path(self) -> str: ...

    # --- Python layer (transferred, disabled until python_enabled) -----------

    @property
    def py_version(self) -> str: ...

    @property
    def android_py_version(self) -> str: ...

    @property
    def uv_py_version(self) -> str: ...

    def install_cpython(self) -> None: ...

    def android_prefix(self, root: Path, arch: str, android_version: str) -> Path: ...


@runtime_checkable
class XcodeProjectDelegate(Protocol):
    @property
    def working_dir(self) -> Path: ...

    @property
    def swift_executable(self) -> str: ...

    @property
    def swift_env(self) -> dict[str, str]: ...

    def xcode_generate(self, *, spec_path: Path, project_dir: Path) -> None: ...

    # --- Python layer (transferred, disabled until python_enabled) -----------

    @property
    def py_version(self) -> str: ...

    @property
    def uv_py_version(self) -> str: ...

    def install_cpython(self) -> None: ...


class BootstrapProtocol(Protocol):
    @property
    def delegate(self) -> ProjectDelegate: ...

    def generate(self, *, platform: str, **kw: object) -> Path | None:
        """Write the native project for ``platform`` ("android", "apple", "desktop")."""
        ...

    def android_templates(self) -> dict[str, str]:
        """Editable template files (name -> default content) at the project root."""
        ...

    def app_target(self) -> str:
        """The app's Swift target: the desktop executable `swift run` runs."""
        ...

    def build_env(self) -> dict[str, str]:
        """Environment every Swift build of the app needs (nucleant.toml [swift.env])."""
        ...

    def install_frameworks(self) -> None: ...

    def sync_site_xcframeworks(self) -> None: ...
