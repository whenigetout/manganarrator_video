# app/config.py

import yaml
from pathlib import Path
from app.utils import log_exception


class VideoConfig:
    def __init__(self, config_path="config.yaml"):
        """
        Load video-related configuration from YAML and validate it.
        """
        self.root = Path(__file__).parent.parent
        self.config = self._load_yaml(self.root / config_path)

        try:
            # Output
            self.output_folder = self.root / self.config.get("output_folder", "output")

            # Clip defaults
            self.default_fps = self.config.get("default_fps", 24)
            self.max_height = self.config.get("max_height", 1080)
            self.max_width = self.config.get("max_width")   # None if not set
            self.pix_fmt = self.config.get("pix_fmt", "yuv420p")
            self.sar = self.config.get("sar", 1)
            self.loop = self.config.get("loop", 1)

            # Render defaults
            self.vcodec = self.config.get("vcodec", "h264_nvenc")
            self.cq = self.config.get("cq", 23)
            self.preset = self.config.get("preset", "p5")
            self.tune = self.config.get("tune", "hq")
            self.fade_s = self.config.get("fade_s", 0.5)
            self.transition = self.config.get("transition", "fade")
            self.audio_fade = self.config.get("audio_fade", "acrossfade")
            self.overwrite = self.config.get("overwrite", True)
            self.verbose = self.config.get("verbose", False)

            # NEW: process capture flags
            self.capture_stderr = self.config.get("capture_stderr", True)
            self.capture_stdout = self.config.get("capture_stdout", False)

            self.max_width = self.config.get("max_width", 1080)
            self.max_height = self.config.get("max_height", 1920)
            self.input_root = self.config.get("input_root", None)
            self.output_root = self.config.get("output_root", None)

            # Run validation automatically
            self.validate()

        except Exception as e:
            log_exception(f"Failed to parse video config values: {e}")
            raise

    def _load_yaml(self, path: Path):
        """
        Safely load a YAML file.
        """
        if not path.exists():
            raise FileNotFoundError(f"Missing YAML config: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            log_exception(f"YAML syntax error in {path}: {e}")
            raise
        except Exception as e:
            log_exception(f"Unexpected error while loading {path}: {e}")
            raise

    def validate(self):
        """
        Validate key config values. Raises ValueError if invalid.
        """
        errors = []

        if self.default_fps <= 0:
            errors.append("default_fps must be > 0")
        if self.max_height is not None and self.max_height <= 0:
            errors.append("max_height must be > 0 if set")
        if self.max_width is not None and self.max_width <= 0:
            errors.append("max_width must be > 0 if set")
        if not isinstance(self.pix_fmt, str) or not self.pix_fmt:
            errors.append("pix_fmt must be a non-empty string")
        if self.sar <= 0:
            errors.append("sar must be > 0")
        if self.loop not in (0, 1):
            errors.append("loop must be 0 or 1")
        if not isinstance(self.vcodec, str) or not self.vcodec:
            errors.append("vcodec must be a non-empty string")
        if self.cq < 0:
            errors.append("cq must be >= 0")
        if not isinstance(self.transition, str) or not self.transition:
            errors.append("transition must be a non-empty string")
        if not isinstance(self.audio_fade, str) or not self.audio_fade:
            errors.append("audio_fade must be a non-empty string")

        if errors:
            raise ValueError("Invalid VideoConfig:\n- " + "\n- ".join(errors))
