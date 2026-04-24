"""Re-export from shared module for backward compatibility."""
from shared.stt import ParaformerStt, SttError  # noqa: F401

__all__ = ["ParaformerStt", "SttError"]
