"""Re-export from shared module for backward compatibility."""
from voice_input_common.audio import (  # noqa: F401
    Recorder,
    RecorderError,
    pcm_rms,
    pcm_to_wav,
)

__all__ = ["Recorder", "RecorderError", "pcm_rms", "pcm_to_wav"]
