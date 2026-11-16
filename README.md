# nucleant-bootstraps

Project generators used by [NucleantProject](https://github.com/NucleantUI/NucleantProject)
(the `nucleant` CLI). A bootstrap turns a project's `nucleant.toml` into the
native projects each platform builds from. It never resolves a toolchain
itself: the CLI hands it a *delegate* that knows the paths.

Cloned from the `nucleant` bootstrap of ksp-bootstraps; the kivy bootstrap and
the pyproject.toml model were left behind.

## Bootstraps

| name | what it generates |
| --- | --- |
| `nucleantui` (default) | a NucleantUI app on every platform, from one `[swift]` table |

`nucleantui` writes:

- **desktop** — the project's `Package.swift` (one executable target over the
  app's sources), for `swift run` on macOS and Linux;
- **android** — `project_dist/gradle`: a Gradle project whose `MainActivity`
  extends NucleantApplication's `org.nucleantui.NucleantActivity`. It compiles
  the `Android/java` of every package in the Swift graph (NucleantApplication's
  Activity, and any package's Java its Swift calls into), staged after the
  Swift build from the packages SwiftPM resolved. Next to it is the Main Swift Package
  (`project_dist/gradle/swift`) that Gradle cross-compiles per ABI with the
  pinned Swift toolchain and Swift Android SDK, staging `libNucleantMain.so`,
  the Swift runtime (Foundation and Observation included) and the vendored
  native libraries into `jniLibs/<abi>`;
- **apple** — `project_dist/xcode`: an XcodeGen project with one iOS + macOS
  app target over the same sources, modeled on NucleantUI's
  `Examples/xcode/project.yml`.

Other NucleantUI app setups can be added beside it with
`register_bootstrap(name, factory)`.

## Layout

```
src/nucleant_bootstraps/
  bootstrap.py          delegate + bootstrap protocols
  config_models.py      the nucleant.toml shape a bootstrap reads
  bootstraps/nucleantui/
    swift_config.py         [nucleantui] + [swift] parsing, dependencies
    swift_package_files.py  Android Main Swift Package + desktop Package.swift
    gradle_builder.py       Android project
    gradle_build_files.py   Gradle/Kotlin DSL templates and tasks
    xcode_builder.py        XcodeGen project
    spec_merge.py           xcode.yaml overlay
  platforms.py          Python layer: pip platforms per slice
  python/               Python layer: Xcode build phases
```

## The Python layer

Embedded CPython (site-packages per ABI/slice, the stdlib, Python services) is
carried over from ksp-bootstraps but **off**: it is only reached when the
config reports `python_enabled`, which NucleantProject does not do yet.
