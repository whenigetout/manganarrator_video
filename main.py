from app.config import VideoConfig
from app.chapter_video_builder import ChapterVideoBuilder

cfg = VideoConfig("config.yaml")
builder = ChapterVideoBuilder(cfg, resolution=(1080,1920), safe_margin=200)
builder.build_run("api_batch_20250821_235731_44f8f3b5", 
                  verbose=True,
                  capture_stderr=False,
                  capture_stdout=False
                  )
