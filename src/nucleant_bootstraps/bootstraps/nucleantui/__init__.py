"""The nucleantui bootstrap: a NucleantUI app on every platform.

One app — a ``@main struct …: NucleantApp`` and the Swift around it — reaches
each platform through the native project that platform builds from:

* **desktop** (macOS, Linux): the project's own ``Package.swift``, built with
  ``swift run``;
* **android**: a Gradle project whose ``MainActivity`` extends
  NucleantApplication's ``NucleantActivity``, and a Main Swift Package Gradle
  cross-compiles per ABI, which depends on the project's package by path;
* **apple**: an XcodeGen project for iOS and the macOS ``.app``, compiling the
  app's target with the packages it uses there.

The project's ``Package.swift`` is the one place the app's Swift is described.
``nucleant init`` writes a starter one; nothing rewrites it. The
rendering itself is Vulkan on a surface the platform's own view class hosts —
CAMetalLayer on Apple, a SurfaceView on Android — with no SDL in between.

Later NucleantUI app setups (other modes) become sibling bootstraps; this one
is the default.
"""

from __future__ import annotations

from pathlib import Path

from ...bootstrap import GradleProjectDelegate, ProjectDelegate, XcodeProjectDelegate
from ...config_models import NucleantTomlProtocol
from .gradle_build_files import (
    DEFAULT_ANDROID_MANIFEST_TEMPLATE,
    DEFAULT_BUILD_GRADLE_TEMPLATE,
)
from .root_package import require_root_package, write_root_package
from .swift_config import SwiftAppConfig, load_swift_config

ANDROID_TEMPLATE_FILES = {
    "build.tmpl.gradle.kts": DEFAULT_BUILD_GRADLE_TEMPLATE,
    "AndroidManifest.tmpl.xml": DEFAULT_ANDROID_MANIFEST_TEMPLATE,
}


class NucleantUIBootstrap:

    name = "nucleantui"

    def __init__(self, config: NucleantTomlProtocol, delegate: ProjectDelegate) -> None:
        self.config = config
        self._delegate = delegate

    @property
    def delegate(self) -> ProjectDelegate:
        return self._delegate

    @property
    def swift(self) -> SwiftAppConfig:
        apple = self.config.apple
        ios = apple.ios if apple else None
        macos = apple.macos if apple else None
        return load_swift_config(
            self.delegate.working_dir,
            self.config.data,
            self.config.app_name,
            ios_deployment=ios.minimum_deployment if ios else None,
            macos_deployment=macos.minimum_deployment if macos else None,
        )

    def generate(self, *, platform: str, **kw) -> Path | None:
        delegate = self.delegate
        match platform:
            case "desktop":
                # `swift run` builds the project's own package; only a project
                # without one (a fresh `nucleant init`) gets the starter.
                if kw.get("init"):
                    return write_root_package(self.swift)
                return require_root_package(self.swift)
            case "android":
                if not isinstance(delegate, GradleProjectDelegate):
                    raise TypeError("android generation needs a GradleProjectDelegate")
                from .gradle_builder import NucleantUIGradleBuilder

                return NucleantUIGradleBuilder(self.config, self.swift, delegate).generate(**kw)
            case "apple":
                if not isinstance(delegate, XcodeProjectDelegate):
                    raise TypeError("apple generation needs an XcodeProjectDelegate")
                from .xcode_builder import NucleantUIXcodeBuilder

                return NucleantUIXcodeBuilder(self.config, self.swift, delegate).generate(**kw)
            case _:
                raise NotImplementedError(f"nucleantui has no {platform!r} project")

    def android_templates(self) -> dict[str, str]:
        return dict(ANDROID_TEMPLATE_FILES)

    def app_target(self) -> str:
        return self.swift.target

    def build_env(self) -> dict[str, str]:
        return self.swift.env_dict

    # --- Python layer (no-ops until it is enabled) ---------------------------

    def install_frameworks(self) -> None:
        """Python.xcframework into project_dist/xcode/Frameworks."""
        if self.config.python_enabled and isinstance(self.delegate, XcodeProjectDelegate):
            self.delegate.install_cpython()

    def sync_site_xcframeworks(self) -> None:
        """Regenerate the Xcode project when site-packages brought new xcframeworks."""
        if self.config.python_enabled and isinstance(self.delegate, XcodeProjectDelegate):
            from .xcode_builder import NucleantUIXcodeBuilder

            NucleantUIXcodeBuilder(self.config, self.swift, self.delegate).generate()
