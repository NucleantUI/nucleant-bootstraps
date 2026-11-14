import re

REPLACE_CHARS = ["-", ".", " "]

RESOLVE_REGEX = rf"[{''.join(REPLACE_CHARS)}]"


def resolve_module_name(name: str) -> str:
    """``My-App.x`` -> ``my_app_x``: the name a module or target is given."""
    return re.sub(RESOLVE_REGEX, "_", name.strip()).lower()


def swift_identifier(name: str) -> str:
    """A name usable as a Swift target / type name: ``my-app`` -> ``MyApp``.

    Keeps an already CamelCase name as it is, so ``NucleantAppTest`` stays
    ``NucleantAppTest``.
    """
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", name.strip()) if p]
    if not parts:
        raise ValueError(f"cannot derive a Swift identifier from {name!r}")
    ident = "".join(p[:1].upper() + p[1:] for p in parts)
    if ident[0].isdigit():
        ident = "App" + ident
    return ident
