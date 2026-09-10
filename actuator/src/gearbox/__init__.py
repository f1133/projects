"""Design and analysis of the actuator's cycloidal gearbox.

The core of the package is deliberately dependency-free -- it needs nothing
beyond the standard library, so the numbers can be checked anywhere without a
toolchain. Only the CAD export under ``cad/`` pulls in build123d.

Typical use::

    from gearbox import config, report
    design = config.load("config/gearbox.toml")
    print(report.render(design))
"""

from __future__ import annotations

from .config import ConfigError, Design, load

__all__ = ["ConfigError", "Design", "load", "__version__"]

__version__ = "0.1.0"
