"""The Python layer, carried over from ksp-bootstraps and switched off.

NucleantUI apps are pure Swift for now. These modules keep what the kivy-era
bootstraps did for embedded CPython — site-packages platforms, XcodeGen build
phases that install ``site_packages`` and the stdlib — so the layer can come
back on top of NucleantUI without being rewritten. Nothing imports them unless
a project's config reports ``python_enabled``.
"""
