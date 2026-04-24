"""CashInFlash deterministic underwriting engine (v2)."""

from .orchestrator import run_v2, V2Result

__version__ = "0.1.0"
__all__ = ["run_v2", "V2Result"]
