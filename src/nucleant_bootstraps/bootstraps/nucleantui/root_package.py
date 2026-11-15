"""The project's own Package.swift: the starter ``nucleant init`` writes, and
what the generators read back out of it.

The root package is the one source of truth for the app's Swift. Nothing
rewrites it. The Android Main Swift Package depends on it by path, so SwiftPM
evaluates it there with Gradle's environment (``ANDROID_BUILD=1``) and
whatever logic it holds applies as written. The Xcode project cannot depend on
an executable, so it reads the manifest instead: ``swift package
dump-package`` evaluates it the same way SwiftPM would and reports the
target's sources and the packages it uses.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .swift_config import SwiftAppConfig, SwiftConfigError

NUCLEANTUI_URL = "https://github.com/NucleantUI/NucleantUI.git"


# ---------------------------------------------------------------------------
# The starter Package.swift
# ---------------------------------------------------------------------------


def root_package_swift(config: SwiftAppConfig) -> str:
    """The Package.swift ``nucleant init`` writes for a new app."""
    t = config.target
    return f"""\
// swift-tools-version: 6.2
//
// The app's package. It is yours: `nucleant init` wrote it once and nucleant
// never rewrites it. Every platform builds the app from here:
//
//   macOS / Linux   `swift run` builds the executable target below.
//   Android         The Gradle project's Swift package (project_dist/gradle/
//                   swift) depends on this one by path and links the
//                   `{t}` library into libNucleantMain.so. Gradle runs
//                   `swift build` with ANDROID_BUILD=1, which is what turns
//                   the target into a library.
//   iOS / .app      The Xcode project compiles `Sources/{t}` and takes the
//                   packages `{t}` depends on.
//
// So declare dependencies here, with whatever version rules and environment
// switches they need, as in any other package.

import Foundation
import PackageDescription

let environment = ProcessInfo.processInfo.environment

/// Android is a cross-compile, and Package.swift is evaluated on the host, so
/// `#if os(Android)` here would describe the build machine. Gradle sets
/// ANDROID_BUILD (and SWIFT_ANDROID_HOME) instead; every Nucleant package
/// reads the same signal.
let isAndroid = environment["ANDROID_BUILD"] != nil
    || environment["SWIFT_ANDROID_HOME"] != nil

let dependencies: [Package.Dependency] = [
    .package(url: "{NUCLEANTUI_URL}", branch: "master"),
]

let appDependencies: [Target.Dependency] = [
    .product(name: "NucleantUI", package: "NucleantUI"),
]

/// On Android the app is a library linked into the Activity's native
/// library, so its entry type (`{config.entry or t + "App"}`) is public. Everywhere else
/// it is the executable `swift run` starts.
let app: Target = isAndroid
    ? .target(name: "{t}", dependencies: appDependencies, path: "Sources/{t}")
    : .executableTarget(name: "{t}", dependencies: appDependencies, path: "Sources/{t}")

let product: Product = isAndroid
    ? .library(name: "{t}", targets: ["{t}"])
    : .executable(name: "{t}", targets: ["{t}"])

let package = Package(
    name: "{t}",
    platforms: [.macOS("{config.macos_deployment}"), .iOS("{config.ios_deployment}")],
    products: [product],
    dependencies: dependencies,
    targets: [app]
)
"""


def write_root_package(config: SwiftAppConfig) -> Path:
    """Write the starter Package.swift unless the project already has one."""
    manifest = config.root_manifest
    if manifest.is_file():
        return config.root_package
    config.root_package.mkdir(parents=True, exist_ok=True)
    manifest.write_text(root_package_swift(config), encoding="utf-8")
    print(f"[nucleant] wrote {manifest}")
    return config.root_package


def require_root_package(config: SwiftAppConfig) -> Path:
    if not config.root_manifest.is_file():
        raise SwiftConfigError(
            f"No Package.swift at {config.root_package}. The app's Swift package "
            "is the project's own: run `nucleant init` to write a starter one."
        )
    return config.root_package


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PackageDependency:
    """One entry of the root package's ``dependencies:``."""

    identity: str
    #: The name ``.product(…, package:)`` refers to it by, when one was given.
    name: str | None
    path: Path | None
    url: str | None
    #: dump-package's requirement: {"range": [...]}, {"branch": [...]}, ...
    requirement: dict

    def matches(self, package: str) -> bool:
        p = package.lower()
        return p == self.identity or (self.name is not None and p == self.name.lower())

    def as_xcodegen_package(self, relative_to: Path) -> dict:
        """The entry under XcodeGen's ``packages:``."""
        if self.path is not None:
            return {"path": Path(os.path.relpath(self.path, relative_to)).as_posix()}
        spec: dict = {"url": self.url}
        req = self.requirement
        if "branch" in req:
            spec["branch"] = req["branch"][0]
        elif "revision" in req:
            spec["revision"] = req["revision"][0]
        elif "exact" in req:
            spec["exactVersion"] = req["exact"][0]
        elif "range" in req:
            lower, upper = req["range"][0]["lowerBound"], req["range"][0]["upperBound"]
            spec.update(_xcodegen_range(lower, upper))
        else:
            raise SwiftConfigError(
                f"Package.swift: {self.identity} has a requirement the Xcode "
                f"project cannot express: {req}"
            )
        return spec


@dataclass(frozen=True)
class RootTarget:
    name: str
    #: "executable", "regular" (a library target), "test", ...
    type: str
    #: Absolute path of its sources.
    path: Path
    #: (product, package) for each ``.product(name:package:)`` it depends on.
    products: tuple[tuple[str, str], ...]
    #: Dependencies on other targets of the root package, by name.
    local: tuple[str, ...]


@dataclass(frozen=True)
class RootPackage:
    directory: Path
    dependencies: tuple[PackageDependency, ...]
    targets: dict[str, RootTarget]
    #: product name -> "library" / "executable" / ...
    products: dict[str, str]

    def target(self, name: str) -> RootTarget:
        if name not in self.targets:
            raise SwiftConfigError(
                f"{self.directory / 'Package.swift'} has no target {name!r} "
                f"(it has {', '.join(self.targets) or 'none'}); nucleant.toml "
                "[swift] target names the app's target."
            )
        return self.targets[name]

    def dependency(self, package: str) -> PackageDependency:
        for dep in self.dependencies:
            if dep.matches(package):
                return dep
        raise SwiftConfigError(
            f"{self.directory / 'Package.swift'}: no dependency named {package!r}"
        )

    @property
    def path_dependencies(self) -> list[Path]:
        return [d.path for d in self.dependencies if d.path is not None]


def dump_root_package(
    config: SwiftAppConfig,
    swift_executable: str,
    env: dict[str, str] | None = None,
) -> RootPackage:
    """Evaluate the root Package.swift (``swift package dump-package``) with
    ``env`` added to the environment, as SwiftPM would for that build."""
    root = require_root_package(config)
    result = subprocess.run(
        [swift_executable, "package", "dump-package", "--package-path", str(root)],
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SwiftConfigError(
            f"`swift package dump-package` failed for {root / 'Package.swift'}:\n"
            f"{result.stderr.strip()}"
        )
    return parse_dump(root, json.loads(result.stdout))


def parse_dump(root: Path, data: dict) -> RootPackage:
    deps = []
    for entry in data.get("dependencies", []):
        if "fileSystem" in entry:
            fs = entry["fileSystem"][0]
            path = Path(fs["path"])
            if not path.is_absolute():
                path = (root / path).resolve()
            deps.append(
                PackageDependency(
                    identity=fs["identity"],
                    name=fs.get("nameForTargetDependencyResolutionOnly"),
                    path=path,
                    url=None,
                    requirement={},
                )
            )
        elif "sourceControl" in entry:
            sc = entry["sourceControl"][0]
            location = sc["location"]
            if "remote" in location:
                remote = location["remote"][0]
                url = remote["urlString"] if isinstance(remote, dict) else remote
            else:  # a local git repository, by path
                local = location["local"][0]
                url = local if isinstance(local, str) else local.get("path")
            deps.append(
                PackageDependency(
                    identity=sc["identity"],
                    name=sc.get("nameForTargetDependencyResolutionOnly"),
                    path=None,
                    url=url,
                    requirement=sc.get("requirement", {}),
                )
            )
        # Registry dependencies have no Xcode or path spelling; skipped.

    targets = {}
    for t in data.get("targets", []):
        products, local = [], []
        for dep in t.get("dependencies", []):
            if "product" in dep:
                name, package = dep["product"][0], dep["product"][1]
                products.append((name, package or name))
            elif "byName" in dep:
                local.append(dep["byName"][0])
            elif "target" in dep:
                local.append(dep["target"][0])
        rel = t.get("path") or f"Sources/{t['name']}"
        targets[t["name"]] = RootTarget(
            name=t["name"],
            type=t.get("type", "regular"),
            path=(root / rel).resolve(),
            products=tuple(products),
            local=tuple(local),
        )

    products = {p["name"]: next(iter(p.get("type", {"library": None}))) for p in data.get("products", [])}
    return RootPackage(directory=root, dependencies=tuple(deps), targets=targets, products=products)


def _xcodegen_range(lower: str, upper: str) -> dict:
    """SwiftPM's version range as XcodeGen spells it."""
    lo = [int(x) for x in lower.split("-")[0].split(".")]
    hi = [int(x) for x in upper.split("-")[0].split(".")]
    if hi == [lo[0] + 1, 0, 0]:
        return {"from": lower}
    if hi == [lo[0], lo[1] + 1, 0]:
        return {"minorVersion": lower}
    return {"minVersion": lower, "maxVersion": upper}
