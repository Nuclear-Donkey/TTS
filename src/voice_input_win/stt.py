"""Re-export from shared module for backward compatibility."""
from voice_input_common.stt import ParaformerStt, SttError  # noqa: F401

__all__ = ["ParaformerStt", "SttError"]
