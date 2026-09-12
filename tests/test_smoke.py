import importlib
import pkgutil

import paperdeck


def test_every_package_module_imports_without_side_effects() -> None:
    names = [info.name for info in pkgutil.walk_packages(paperdeck.__path__, "paperdeck.")]
    for name in names:
        importlib.import_module(name)
