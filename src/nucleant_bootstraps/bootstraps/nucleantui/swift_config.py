"""The ``[swift]`` table of ``nucleant.toml``, read by the nucleantui bootstrap.

The app's Swift is an ordinary Swift package: the ``Package.swift`` at the
project root. It is the project's own — ``nucleant init`` writes a starter one
and nothing rewrites it — so every dependency, version rule and environment
switch lives there, written the way every Nucleant package writes them.
nucleant.toml does not list packages.

``[swift]`` only says which part of that package the platforms start::

    [swift]
    # The app's target in Package.swift: an executable for `swift run`, and a
    # library product of the same name when ANDROID_BUILD is set, which the
    # Android Main Swift Package links.
    target = "MyApp"
    # The NucleantApp type the Android Activity starts (public, with a
    # public init()).
    entry = "MyAppApp"
    # package = "."                                  # the directory of that Package.swift
    # android_package = "project_dist/gradle/swift"  # the generated Android package

    [swift.env]
    # NUCLEANT_ANDROID_USE_AHARDWAREBUFFER = "1"

How each platform gets at the package:

* **macOS / Linux** — ``swift run`` in it.
* **Android** — the generated Main Swift Package depends on it by path
  (``.package(path: "../../..")``) and links its ``target`` library product.
* **iOS / the macOS .app** — the Xcode project compiles the target's sources
  and takes the packages the target depends on, as ``swift package
  dump-package`` reports them (see ``root_package``).
"""

from __future__ import annotations

import os.path
from dataclasses import dataclass
from pathlib import Path

from ...tools import swift_identifier

DEFAULT_ANDROID_PACKAGE = "project_dist/gradle/swift"
DEFAULT_MACOS_DEPLOYMENT = "14.0"
DEFAULT_IOS_DEPLOYMENT = "17.0"

#: Written into every Package.swift nucleant generates, so a later run can tell
#: its own output from a manifest the project wrote by hand. The project's root
#: Package.swift does not carry it: that one is never regenerated.
GENERATED_MARKER = "nucleant:generated-swift-package"
#: Packages ksproject's nucleant bootstrap generated are ours to refresh too.
_LEGACY_MARKERS = ("ksproject:generated-main-swift-package",)

#: Keys nucleant.toml used to describe the package with. Package.swift says
#: all of this now; a project still using them gets told where it went.
_MOVED_TO_PACKAGE_SWIFT = {
    "dependencies": "[[swift.dependencies]]",
    "sources": "[swift] sources",
    "unsafe_flags": "[swift] unsafe_flags",
}


class SwiftConfigError(Exception):
    pass


@dataclass(frozen=True)
class SwiftAppConfig:
    """``[swift]``, resolved against the project directory."""

    project_dir: Path
    #: The app's target in the root package, and the library product of the
    #: same name the Android package links.
    target: str
    #: The NucleantApp-conforming type; None means "no app", see has_app.
    entry: str | None
    #: Absolute path of the project's own package (its Package.swift).
    root_package: Path
    #: Absolute path of the generated Android Main Swift Package.
    android_package: Path
    #: Environment for every Swift build of this app. Package.swift can only
    #: read the environment, so choices made there (such as
    #: NUCLEANT_ANDROID_USE_AHARDWAREBUFFER) have to come in this way.
    env: tuple[tuple[str, str], ...] = ()
    macos_deployment: str = DEFAULT_MACOS_DEPLOYMENT
    ios_deployment: str = DEFAULT_IOS_DEPLOYMENT

    @property
    def has_app(self) -> bool:
        """Whether an app entry type was configured at all.

        Without one the Android package still builds — it is then just the JNI
        bridge and whatever the root package brings, which is a useful thing to
        be able to compile on its own.
        """
        return self.entry is not None

    @property
    def env_dict(self) -> dict[str, str]:
        return dict(self.env)

    @property
    def root_manifest(self) -> Path:
        return self.root_package / "Package.swift"

    @property
    def root_identity(self) -> str:
        """SwiftPM's identity for the root package as a path dependency: its
        directory name, lowercased — what ``package:`` names it by."""
        return self.root_package.name.lower()

    @property
    def android_package_is_foreign(self) -> bool:
        return is_foreign_package(self.android_package)


def load_swift_config(
    project_dir: Path,
    data: dict,
    app_name: str,
    ios_deployment: str | None = None,
    macos_deployment: str | None = None,
) -> SwiftAppConfig:
    """Parse ``[swift]`` out of a project's raw ``nucleant.toml`` data.

    A missing table is not an error: the target defaults to the app name as a
    Swift identifier, the package to the project directory.
    """
    section: dict = data.get("swift", {}) or {}
    project_dir = Path(project_dir).resolve()
    _reject_package_keys(data, section)

    return SwiftAppConfig(
        project_dir=project_dir,
        target=section.get("target") or swift_identifier(app_name),
        entry=section.get("entry"),
        root_package=_resolve(project_dir, section.get("package", ".")),
        android_package=_resolve(
            project_dir, section.get("android_package", DEFAULT_ANDROID_PACKAGE)
        ),
        env=tuple(
            (str(k), str(v)) for k, v in (section.get("env", {}) or {}).items()
        ),
        macos_deployment=str(
            macos_deployment or section.get("macos") or DEFAULT_MACOS_DEPLOYMENT
        ),
        ios_deployment=str(
            ios_deployment or section.get("ios") or DEFAULT_IOS_DEPLOYMENT
        ),
    )


def _reject_package_keys(data: dict, section: dict) -> None:
    moved = [label for key, label in _MOVED_TO_PACKAGE_SWIFT.items() if key in section]
    if "nucleantui" in data:
        moved.insert(0, "[nucleantui]")
    if moved:
        raise SwiftConfigError(
            f"nucleant.toml: {', '.join(moved)} {'is' if len(moved) == 1 else 'are'} "
            "gone — the app's packages, sources and flags are declared in its own "
            "Package.swift now (NucleantUI included), and every platform builds "
            "from that. Move them there and delete them from nucleant.toml."
        )


def portable_relpath(target: Path, start: Path) -> str:
    """``target`` relative to ``start`` when they share a parent below the
    filesystem root; absolute otherwise (a path climbing to ``/`` is no more
    movable than an absolute one, and much harder to read)."""
    target, start = Path(target), Path(start)
    try:
        common = Path(os.path.commonpath([target, start]))
    except ValueError:  # different drives on Windows
        return target.as_posix()
    if common == Path(common.anchor):
        return target.as_posix()
    return Path(os.path.relpath(target, start)).as_posix()


def _resolve(project_dir: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (project_dir / p).resolve()


def is_foreign_package(package_dir: Path) -> bool:
    """Whether ``package_dir`` holds a Package.swift this generator did not write.

    Existence alone cannot answer this: the generator's own output exists from
    the second run onwards, and treating that as the project's would freeze the
    manifest at whatever the first run produced. Deleting the marker line hands
    a manifest to the project.
    """
    manifest = package_dir / "Package.swift"
    if not manifest.is_file():
        return False
    text = manifest.read_text(encoding="utf-8")
    return not any(m in text for m in (GENERATED_MARKER, *_LEGACY_MARKERS))
