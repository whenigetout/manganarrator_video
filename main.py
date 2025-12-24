from app.config import VideoConfig
from app.chapter_video_builder import ChapterVideoBuilder
import json
from pathlib import Path
from typing import Tuple, List

cfg = VideoConfig("config.yaml")
builder = ChapterVideoBuilder(cfg, resolution=(1080,1920), safe_margin=200)
builder.build_run("test", 
                  verbose=True,
                  capture_stderr=False,
                  capture_stdout=False
                  )
