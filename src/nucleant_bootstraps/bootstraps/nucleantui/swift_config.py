"""The ``[nucleantui]`` and ``[swift]`` tables of ``nucleant.toml``, read by the
nucleantui bootstrap.

What a NucleantUI app's Swift side is made of is this bootstrap's business, so
it parses the table itself from the raw TOML the CLI hands over, rather than
having it typed in NucleantProject's shared model.

Example::

    # NucleantUI is the bootstrap's own dependency: always there, this table
    # only picks which one. Missing table = GitHub, branch master.
    [nucleantui]
    branch = "master"      # or up_to_major = "0.1.0" / exact = "0.1.0"
    # url = "https://github.com/<you>/NucleantUI.git"  # a fork
    # path = "../NucleantUI"                           # a local fork

    [swift]
    # The Swift target the app's sources compile into (desktop executable
    # target name, and the Xcode app target's module).
    target = "MyApp"
    # The NucleantApp-conforming type the Android Activity starts.
    entry = "MyAppApp"
    # The app's own Swift, relative to the project.
    sources = ["Sources/MyApp"]
    # Where the Android Main Swift Package is generated.
    android_package = "project_dist/gradle/swift"

    [swift.env]
    # NUCLEANT_ANDROID_USE_AHARDWAREBUFFER = "1"

    # Packages beyond NucleantUI.
    [[swift.dependencies]]
    name = "Yams"
    url = "https://github.com/jpsim/Yams.git"
    up_to_major = "6.0.0"
    products = ["Yams"]

A dependency takes either ``path`` (relative to the project directory, or
absolute) or ``url`` plus one of ``branch`` / ``up_to_major`` / ``exact``
(``up_to_major`` is SwiftPM's ``from:``). ``[nucleantui]`` takes the same
keys, with ``url`` defaulting to the NucleantUI repository.

The same dependency list feeds all three generated projects — the desktop
``Package.swift``, the Android Main Swift Package and the Xcode project — so
``nucleant.toml`` is the one place a dependency is declared.
"""

from __future__ import annotations

import os.path
from dataclasses import dataclass
from pathlib import Path

from ...tools import swift_identifier

DEFAULT_ANDROID_PACKAGE = "project_dist/gradle/swift"
DEFAULT_MACOS_DEPLOYMENT = "14.0"
DEFAULT_IOS_DEPLOYMENT = "17.0"

NUCLEANTUI_URL = "https://github.com/NucleantUI/NucleantUI.git"
NUCLEANTUI_PRODUCT = "NucleantUI"
DEFAULT_NUCLEANTUI_BRANCH = "master"
_VERSION_KEYS = ("branch", "up_to_major", "exact")

#: Written into every generated Package.swift so a later run can tell its own
#: output from a manifest the project wrote by hand.
GENERATED_MARKER = "nucleant:generated-swift-package"
#: Packages ksproject's nucleant bootstrap generated are ours to refresh too.
_LEGACY_MARKERS = ("ksproject:generated-main-swift-package",)


class SwiftConfigError(Exception):
    pass


@dataclass(frozen=True)
class SwiftDependency:
    """One package the app depends on."""

    name: str
    path: Path | None = None
    url: str | None = None
    branch: str | None = None
    up_to_major: str | None = None
    exact: str | None = None
    products: tuple[str, ...] = ()

    @property
    def identity(self) -> str:
        """SwiftPM's package identity: the checkout or repository name."""
        if self.path is not None:
            return self.path.name.lower()
        if self.url:
            last = self.url.rstrip("/").rsplit("/", 1)[-1]
            return last.removesuffix(".git").lower()
        return self.name.lower()

    @property
    def product_names(self) -> tuple[str, ...]:
        """No products listed means the package name doubles as the product."""
        return self.products or (self.name,)

    def as_package_dependency(self, relative_to: Path | None = None) -> str:
        """The ``.package(...)`` line for a Package.swift in ``relative_to``.

        SwiftPM resolves a path dependency relative to the manifest, so an
        absolute path is rewritten to a relative one where possible. That keeps
        the generated tree movable, and readable in a diff.
        """
        if self.path is not None:
            return f'.package(path: "{self.relative_path(relative_to).as_posix()}")'
        if self.url is None:
            raise SwiftConfigError(
                f"swift dependency {self.name!r} has neither 'path' nor 'url'"
            )
        if self.branch:
            return f'.package(url: "{self.url}", branch: "{self.branch}")'
        if self.exact:
            return f'.package(url: "{self.url}", exact: "{self.exact}")'
        if self.up_to_major:
            return f'.package(url: "{self.url}", from: "{self.up_to_major}")'
        raise SwiftConfigError(
            f"swift dependency {self.name!r} gives a url but no "
            "'branch', 'up_to_major' or 'exact'"
        )

    def relative_path(self, relative_to: Path | None) -> Path:
        assert self.path is not None
        if relative_to is None:
            return self.path
        return Path(portable_relpath(self.path, relative_to))

    def as_target_dependencies(self) -> list[str]:
        """The ``.product(...)`` lines this dependency contributes."""
        return [
            f'.product(name: "{p}", package: "{self.name}")' for p in self.product_names
        ]

    def as_xcodegen_package(self, relative_to: Path) -> dict:
        """The entry under XcodeGen's ``packages:``."""
        if self.path is not None:
            return {"path": self.relative_path(relative_to).as_posix()}
        if self.url is None:
            raise SwiftConfigError(
                f"swift dependency {self.name!r} has neither 'path' nor 'url'"
            )
        spec: dict = {"url": self.url}
        if self.branch:
            spec["branch"] = self.branch
        elif self.exact:
            spec["exactVersion"] = self.exact
        elif self.up_to_major:
            spec["from"] = self.up_to_major
        else:
            raise SwiftConfigError(
                f"swift dependency {self.name!r} gives a url but no "
                "'branch', 'up_to_major' or 'exact'"
            )
        return spec


@dataclass(frozen=True)
class SwiftAppConfig:
    """``[swift]``, resolved against the project directory."""

    project_dir: Path
    #: The Swift target (and module) the app's sources compile into.
    target: str
    #: The NucleantApp-conforming type; None means "no app", see has_app.
    entry: str | None
    sources: tuple[Path, ...]
    #: Absolute path of the Android Main Swift Package.
    android_package: Path
    #: Absolute path of the desktop package (the one `swift run` builds).
    desktop_package: Path
    #: NucleantUI first, then ``[[swift.dependencies]]``.
    dependencies: tuple[SwiftDependency, ...] = ()
    unsafe_flags: tuple[str, ...] = ()
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
        bridge and whatever the dependencies bring, which is a useful thing to
        be able to compile on its own.
        """
        return self.entry is not None

    @property
    def env_dict(self) -> dict[str, str]:
        return dict(self.env)

    @property
    def android_package_is_foreign(self) -> bool:
        return is_foreign_package(self.android_package)

    @property
    def desktop_package_is_foreign(self) -> bool:
        return is_foreign_package(self.desktop_package)


def load_swift_config(
    project_dir: Path,
    data: dict,
    app_name: str,
    ios_deployment: str | None = None,
    macos_deployment: str | None = None,
) -> SwiftAppConfig:
    """Parse ``[swift]`` out of a project's raw ``nucleant.toml`` data.

    A missing table is not an error: the defaults put the app's sources at
    ``Sources/<Target>`` with no dependencies and no entry type, and the caller
    decides whether that is usable.
    """
    section: dict = data.get("swift", {}) or {}
    project_dir = Path(project_dir).resolve()

    target = section.get("target") or swift_identifier(app_name)

    raw_sources = section.get("sources")
    if raw_sources is None:
        default = project_dir / "Sources" / target
        sources = (default,) if default.is_dir() else ()
    else:
        sources = tuple(_resolve(project_dir, s) for s in raw_sources)
    for src in sources:
        if not src.is_dir():
            raise SwiftConfigError(f"[swift] sources: {src} is not a directory")

    nucleantui = nucleantui_dependency(project_dir, data)
    extra = tuple(
        _dependency(project_dir, entry)
        for entry in section.get("dependencies", []) or []
    )
    for dep in extra:
        if dep.identity == nucleantui.identity or dep.name.lower() == "nucleantui":
            raise SwiftConfigError(
                f"[[swift.dependencies]] lists {dep.name!r}, but NucleantUI is the "
                "nucleantui bootstrap's own dependency: pick its version or fork "
                "in [nucleantui] instead"
            )
    dependencies = (nucleantui, *extra)

    return SwiftAppConfig(
        project_dir=project_dir,
        target=target,
        entry=section.get("entry"),
        sources=sources,
        android_package=_resolve(
            project_dir, section.get("android_package", DEFAULT_ANDROID_PACKAGE)
        ),
        desktop_package=_resolve(project_dir, section.get("package", ".")),
        dependencies=dependencies,
        unsafe_flags=tuple(section.get("unsafe_flags", []) or []),
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


def nucleantui_dependency(project_dir: Path, data: dict) -> SwiftDependency:
    """NucleantUI, as ``[nucleantui]`` picks it (default: GitHub, branch master).

    A fork keeps its own package name — its repository or directory name —
    while the product stays ``NucleantUI``.
    """
    section: dict = data.get("nucleantui", {}) or {}
    where = "[nucleantui]"
    unknown = set(section) - {"url", "path", "from", *_VERSION_KEYS}
    if unknown:
        raise SwiftConfigError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")
    path = _dependency_path(project_dir, section, where)
    versions = _versions(section, where)
    if path is not None:
        if section.get("url") or any(versions.values()):
            raise SwiftConfigError(f"{where}: 'path' is a local fork and takes no url or version")
        return SwiftDependency(name=path.name, path=path, products=(NUCLEANTUI_PRODUCT,))
    if not any(versions.values()):
        versions["branch"] = DEFAULT_NUCLEANTUI_BRANCH
    url = section.get("url") or NUCLEANTUI_URL
    name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") or "NucleantUI"
    return SwiftDependency(name=name, url=url, products=(NUCLEANTUI_PRODUCT,), **versions)


def _dependency(project_dir: Path, entry: dict) -> SwiftDependency:
    name = entry.get("name")
    if not name:
        raise SwiftConfigError("[[swift.dependencies]] entry has no 'name'")
    where = f"swift dependency {name!r}"
    path = _dependency_path(project_dir, entry, where)
    return SwiftDependency(
        name=name,
        path=path,
        url=entry.get("url"),
        products=tuple(entry.get("products", []) or []),
        **_versions(entry, where),
    )


def _dependency_path(project_dir: Path, entry: dict, where: str) -> Path | None:
    raw_path = entry.get("path")
    path = _resolve(project_dir, raw_path) if raw_path else None
    if path is not None and not path.is_dir():
        raise SwiftConfigError(f"{where}: path {path} does not exist")
    return path


def _versions(entry: dict, where: str) -> dict[str, str | None]:
    """``branch`` / ``up_to_major`` / ``exact``: at most one of them."""
    if "from" in entry:
        raise SwiftConfigError(f"{where}: 'from' is spelled 'up_to_major' in nucleant.toml")
    given = {k: str(entry[k]) for k in _VERSION_KEYS if entry.get(k)}
    if len(given) > 1:
        raise SwiftConfigError(
            f"{where}: give one of {', '.join(_VERSION_KEYS)}, not {' and '.join(given)}"
        )
    return {k: given.get(k) for k in _VERSION_KEYS}


def is_foreign_package(package_dir: Path) -> bool:
    """Whether ``package_dir`` holds a Package.swift this generator did not write.

    Existence alone cannot answer this: the generator's own output exists from
    the second run onwards, and treating that as the project's would freeze the
    manifest at whatever the first run produced — so a changed dependency would
    never reach it. Deleting the marker line hands a manifest to the project.
    """
    manifest = package_dir / "Package.swift"
    if not manifest.is_file():
        return False
    text = manifest.read_text(encoding="utf-8")
    return not any(m in text for m in (GENERATED_MARKER, *_LEGACY_MARKERS))
