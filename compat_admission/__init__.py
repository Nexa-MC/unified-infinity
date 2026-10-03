"""Read-only metadata admission. This package never loads or executes mod code."""
from .core import Limits, Target, plan

__all__ = ["Limits", "Target", "plan"]
__version__ = "0.1.0"
