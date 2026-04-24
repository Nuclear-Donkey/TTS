"""Re-export from shared module for backward compatibility."""
from shared.audio import (  # noqa: F401
    Recorder,
    RecorderError,
    pcm_rms,
    pcm_to_wav,
)

__all__ = ["Recorder", "RecorderError", "pcm_rms", "pcm_to_wav"]
