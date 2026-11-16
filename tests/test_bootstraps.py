from __future__ import annotations

from pathlib import Path

import pytest

from nucleant_bootstraps import BootstrapError, get_bootstrap, register_bootstrap
from nucleant_bootstraps.bootstraps.nucleantui import ANDROID_TEMPLATE_FILES, NucleantUIBootstrap
from nucleant_bootstraps.bootstraps.nucleantui.gradle_build_files import _template_version
from nucleant_bootstraps.bootstraps.nucleantui.swift_config import (
    GENERATED_MARKER,
    is_foreign_package,
    load_swift_config,
)
from nucleant_bootstraps.tools import resolve_module_name, swift_identifier


class Config:
    name = "app"
    app_name = "App"
    bootstrap = "nucleantui"
    android = None
    apple = None
    python_enabled = False
    data: dict = {"swift": {"env": {"NUCLEANT_ANDROID_USE_AHARDWAREBUFFER": "1"}}}


class Delegate:
    working_dir = Path("/nonexistent")
    swift_executable = "swift"
    swift_env: dict = {}


def test_registry():
    assert isinstance(get_bootstrap("nucleantui", Config(), Delegate()), NucleantUIBootstrap)
    with pytest.raises(BootstrapError, match="not a bootstrap"):
        get_bootstrap("kivy", Config(), Delegate())
    register_bootstrap("custom", lambda c, d: "custom-bootstrap")  # type: ignore[arg-type,return-value]
    assert get_bootstrap("custom", Config(), Delegate()) == "custom-bootstrap"


def test_bootstrap_exposes_target_and_env():
    b = get_bootstrap("nucleantui", Config(), Delegate())
    assert b.app_target() == "App"
    assert b.build_env() == {"NUCLEANT_ANDROID_USE_AHARDWAREBUFFER": "1"}


def test_templates_carry_a_version():
    for name, content in ANDROID_TEMPLATE_FILES.items():
        assert _template_version(content) == 1, name


def test_foreign_package_detection(tmp_path: Path):
    assert not is_foreign_package(tmp_path)  # no manifest
    (tmp_path / "Package.swift").write_text(f"// {GENERATED_MARKER}\n")
    assert not is_foreign_package(tmp_path)
    (tmp_path / "Package.swift").write_text("// ksproject:generated-main-swift-package\n")
    assert not is_foreign_package(tmp_path)
    (tmp_path / "Package.swift").write_text("// hand written\n")
    assert is_foreign_package(tmp_path)


def test_swift_config_defaults(tmp_path: Path):
    swift = load_swift_config(tmp_path, {}, "My App")
    assert swift.target == "MyApp"
    assert swift.entry is None and not swift.has_app
    assert swift.android_package == tmp_path.resolve() / "project_dist/gradle/swift"
    assert swift.root_package == tmp_path.resolve()
    assert swift.root_identity == tmp_path.name.lower()


def test_names():
    assert resolve_module_name("My-App.x") == "my_app_x"
    assert swift_identifier("my-app") == "MyApp"
    assert swift_identifier("NucleantAppTest") == "NucleantAppTest"
    assert swift_identifier("2048") == "App2048"


def test_gradle_compiles_every_swift_packages_android_java(tmp_path: Path):
    from enum import StrEnum

    from nucleant_bootstraps.bootstraps.nucleantui.gradle_build_files import GradleBuildFiles

    class Arch(StrEnum):
        X86_64 = "x86_64"

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    GradleBuildFiles.write_app_build_gradle(
        project_dir=tmp_path,
        app_dir=app_dir,
        package_name="org.example.app",
        archs=[Arch.X86_64],
        compile_sdk=36,
        min_sdk=28,
        target_sdk=36,
        swift_main=tmp_path / "swift",
    )
    build = (app_dir / "build.gradle.kts").read_text()

    # Every package's Android/java, staged from the packages SwiftPM resolved...
    assert 'val nucleantJavaDir = layout.buildDirectory.dir("generated/packageJava")' in build
    assert "workspace-state.json" in build
    assert 'tasks.register<Sync>("stagePackageJava")' in build
    assert 'File(it, "Android/java")' in build
    # ...compiled with the app, after it is staged.
    assert "java.srcDir(nucleantJavaDir)" in build
    assert "dependsOn(buildSwiftAll, stagePackageJava)" in build
    # Not one package's Java found by a guess at generation time.
    assert "{nucleant_java_dir}" not in build
    assert "checkouts/NucleantApplication/Android/java" not in build
