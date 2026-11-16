"""Gradle project generation for the nucleantui bootstrap.

The generated app is a plain ``Activity`` — ``MainActivity``, a subclass of
NucleantApplication's ``org.nucleantui.NucleantActivity`` — hosting a
``SurfaceView``, plus a SwiftPM package (the Main Swift Package) that Gradle
cross-compiles for each ABI: app, framework and JNI bridge in one library.

Python is not part of a NucleantUI app for now. The site-packages staging the
kivy-era bootstrap did is carried over in ``GradleBuildFiles`` and switched on
only by ``python_enabled``.
"""

from __future__ import annotations

import glob
import shutil
from pathlib import Path

from ...bootstrap import GradleProjectDelegate
from ...config_models import AndroidProtocol, NucleantTomlProtocol
from .gradle_build_files import GradleBuildFiles
from .root_package import RootPackage, dump_root_package
from .swift_config import SwiftAppConfig, SwiftConfigError
from .swift_package_files import write_swift_package

TEMPLATES_DIR = Path(__file__).parent / "templates"


class NucleantUIGradleBuilder:

    delegate: GradleProjectDelegate
    android: AndroidProtocol

    def __init__(
        self,
        config: NucleantTomlProtocol,
        swift: SwiftAppConfig,
        delegate: GradleProjectDelegate,
    ) -> None:
        if config.android is None:
            raise ValueError("[android] is missing in nucleant.toml")
        self.config = config
        self.swift = swift
        self.delegate = delegate
        self.working_dir = delegate.working_dir
        self.android = config.android
        self.app_name = config.app_name
        self.package_name = self.android.package_name or f"org.nucleantui.{config.name}"
        self.archs = list(self.android.archs)

    # ------------------------------------------------------------------
    # Asset resolution
    # ------------------------------------------------------------------

    def _resolve_asset(self, name: str) -> Path:
        """A user-supplied asset (``[android] icon = "…"``) or the bundled default."""
        user_value: str | None = getattr(self.android, name, None)
        if user_value:
            p = Path(user_value).expanduser()
            return p if p.is_absolute() else self.working_dir / p
        for ext in ("png", "jpg", "gif", "json"):
            candidate = TEMPLATES_DIR / f"{name}.{ext}"
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"No template found for '{name}' in {TEMPLATES_DIR}")

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @property
    def dist_dir(self) -> Path:
        return self.working_dir / "project_dist" / "gradle"

    def generate(
        self,
        sdk_path: str,
        aar: bool = False,
        extra_gradle_dependencies: list[str] | None = None,
        extra_permissions: list[str] | None = None,
    ) -> Path:
        android = self.android
        delegate = self.delegate
        swift = self.swift
        python_enabled = self.config.python_enabled
        dist_dir = self.dist_dir
        dist_dir.mkdir(parents=True, exist_ok=True)

        merged_deps = _merge_unique(
            list(android.gradle_dependencies), extra_gradle_dependencies or []
        )
        merged_perms = _merge_unique(list(android.permissions), extra_permissions or [])

        # Root Gradle files
        GradleBuildFiles.write_root_build_gradle(dist_dir, list(android.gradle_plugins))
        GradleBuildFiles.write_settings_gradle(dist_dir, self.app_name)
        GradleBuildFiles.write_gradle_properties(
            dist_dir,
            swift_path=delegate.swift_executable,
            swift_sdk=delegate.swift_android_sdk,
        )
        GradleBuildFiles.write_local_properties(dist_dir, sdk_path)

        # The app module must exist before `gradle wrapper` evaluates settings.
        app_dir = dist_dir / "app"
        app_dir.mkdir(parents=True, exist_ok=True)

        api = android.api or delegate.default_api_version
        min_sdk = android.min_api or 28

        # nucleant.toml [swift.env] plus whatever the CLI adds for every Swift
        # build (the CLI's values win: they describe the resolved toolchain).
        swift_env = {**swift.env_dict, **delegate.swift_env}

        # The project's Package.swift, as Gradle's `swift build` will see it.
        root = self._android_root_package(swift_env)

        # The Main Swift Package is written before the Gradle files that build
        # it, so a first `nucleant android run` needs no separate step.
        write_swift_package(swift.android_package, swift)

        GradleBuildFiles.write_app_build_gradle(
            project_dir=self.working_dir,
            app_dir=app_dir,
            package_name=self.package_name,
            archs=self.archs,
            compile_sdk=api,
            min_sdk=min_sdk,
            target_sdk=api,
            ndk_version=delegate.ndk_version,
            ndk_path=delegate.ndk_path,
            aar=aar,
            gradle_dependencies=merged_deps,
            version_code=android.version_code,
            version_name=android.version_name,
            post_build=android.post_build,
            swift_main=swift.android_package,
            native_lib_dirs=_vendored_native_roots(root),
            swift_env=tuple(swift_env.items()),
            python_enabled=python_enabled,
            python_version=delegate.py_version if python_enabled else "3.13",
            byte_compile_python=android.byte_compile_python,
            uv_python=delegate.uv_py_version if python_enabled else None,
            app_module=self.config.name,
        )

        main_dir = app_dir / "src" / "main"
        main_dir.mkdir(parents=True, exist_ok=True)
        res_dir = main_dir / "res"
        GradleBuildFiles.write_icon(res_dir, self._resolve_asset("icon"))

        presplash_name, presplash_type = self._write_presplash(res_dir, merged_deps)

        GradleBuildFiles.write_android_manifest(
            main_dir,
            package_name=self.package_name,
            project_dir=self.working_dir,
            app_name=self.app_name,
            permissions=merged_perms,
            meta_data=android.meta_data,
            services=list(android.services) if python_enabled else [],
            entrypoint=self.config.name,
            presplash_name=presplash_name,
            presplash_type=presplash_type,
            presplash_color=android.presplash_color or "#FFFFFF",
        )

        # NucleantActivity and NucleantSurfaceView ship with NucleantApplication
        # (compiled from its Android/java); only this app's subclass is generated.
        GradleBuildFiles.write_main_activity(main_dir=main_dir, package_name=self.package_name)

        # Services run Python entry points; they come back with the Python layer.
        if android.services:
            if python_enabled:
                for svc in android.services:
                    GradleBuildFiles.write_custom_service(
                        main_dir=main_dir,
                        package_name=self.package_name,
                        service_name=svc.name,
                        python_version=delegate.py_version,
                        entrypoint=svc.entrypoint,
                        foreground=svc.foreground,
                        start_type=svc.start_type,
                        notification_title=svc.notification_title,
                        notification_text=svc.notification_text,
                        notification_icon=svc.notification_icon,
                    )
            else:
                print(
                    "[nucleant] [[android.services]] are Python services and the "
                    "Python layer is off — skipping them."
                )

        # The wrapper last, now that the app module exists on disk.
        GradleBuildFiles.write_gradle_wrapper(dist_dir, delegate.java_path)

        self._copy_include_files()

        print(f"Gradle project generated at: {dist_dir}")
        print(f"  {swift.android_package} — the Main Swift Package, built per ABI by Gradle")
        print("  app/build/generated/jniLibs/<abi> — libNucleantMain.so, the Swift runtime")
        print("    and the vendored native libraries, staged at build time")
        return dist_dir

    def _android_root_package(self, swift_env: dict[str, str]) -> RootPackage:
        """The root Package.swift evaluated with Gradle's environment, checked
        for the one thing the Android package needs from it: a library product
        named after ``[swift] target``."""
        swift = self.swift
        root = dump_root_package(
            swift,
            self.delegate.swift_executable,
            {**swift_env, "ANDROID_BUILD": "1"},
        )
        kind = root.products.get(swift.target)
        if kind != "library":
            found = f"a {kind} product" if kind else "no product"
            raise SwiftConfigError(
                f"{swift.root_manifest} has {found} named {swift.target!r} when "
                "ANDROID_BUILD is set. The Android package links the app as a "
                f"library, so declare it as one there:\n"
                f'    .library(name: "{swift.target}", targets: ["{swift.target}"])\n'
                f'    .target(name: "{swift.target}", ...)  // not .executableTarget\n'
                "under `ANDROID_BUILD` — the Package.swift `nucleant init` writes "
                "shows how."
            )
        return root

    def _write_presplash(
        self, res_dir: Path, merged_deps: list[str]
    ) -> tuple[str | None, str | None]:
        """Lottie first, else an image/gif (the bundled one by default)."""
        if self.android.presplash_lottie:
            asset_src = self._resolve_asset("presplash_lottie")
            raw_dir = res_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_src, raw_dir / asset_src.name)
            merged_deps.append("com.airbnb.android:lottie:6.0.0")
            return asset_src.stem, "lottie"
        try:
            asset_src = self._resolve_asset("presplash")
        except FileNotFoundError:
            return None, None
        drawable_dir = res_dir / "drawable"
        drawable_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_src, drawable_dir / asset_src.name)
        kind = "gif" if asset_src.suffix.lower() == ".gif" else "image"
        return asset_src.stem, kind

    def _copy_include_files(self) -> None:
        """``[android] include_files`` (google-services.json and friends)."""
        for dest_str, sources in self.android.include_files:
            target_dir = self.working_dir / "project_dist" / dest_str
            target_dir.mkdir(parents=True, exist_ok=True)

            for src_str in sources:
                if "*" in src_str or "?" in src_str:
                    if Path(src_str).is_absolute():
                        paths = [Path(p) for p in glob.glob(src_str)]
                    else:
                        paths = list(self.working_dir.glob(src_str))
                    if not paths:
                        print(f"[nucleant] Warning: no files matched include_files pattern: {src_str}")
                        continue
                else:
                    src_path = Path(src_str).expanduser()
                    if not src_path.is_absolute():
                        src_path = self.working_dir / src_path
                    if not src_path.exists():
                        print(f"[nucleant] Warning: include_files source not found: {src_path}")
                        continue
                    paths = [src_path]

                for path in paths:
                    if path.is_dir():
                        shutil.copytree(path, target_dir / path.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(path, target_dir / path.name)
                    print(f"[nucleant] Copied include_file: {path.name} -> {target_dir}")


def _merge_unique(base: list[str], extra: list[str]) -> list[str]:
    """Merge two lists preserving order and removing duplicates."""
    return list(dict.fromkeys(base + extra))


def _vendored_native_roots(root: RootPackage) -> list[Path]:
    """Directories holding vendored Android .so files the Swift graph links.

    ``libNucleantMain.so`` needs ThorVG, wgpu, shaderc and spirv-cross at
    runtime, and none of them belong to the package the project names — they
    come from further down the Swift dependency tree. Every Nucleant package
    keeps its Android artifacts at ``Dependencies/android/<abi>/lib``, so the
    siblings of a path dependency of the project's Package.swift are the place
    to look. (Packages resolved from git are scanned by Gradle under the
    scratch checkouts.)
    """
    roots: list[Path] = []
    seen: set[Path] = set()
    for path in root.path_dependencies:
        if not path.is_dir():
            continue
        for candidate in [path, *sorted(path.parent.iterdir())]:
            if not candidate.is_dir():
                continue
            android = candidate / "Dependencies" / "android"
            if android.is_dir() and android not in seen:
                seen.add(android)
                roots.append(android)
    return roots
