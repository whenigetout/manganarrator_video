from app.config import VideoConfig
from app.video_runner import VideoRunner
from pathlib import Path

if __name__ == "__main__":
    # Load global config
    cfg = VideoConfig("config.yaml")

    # Initialize runner
    runner = VideoRunner(cfg)

    # Run pipeline
    result = runner.run_single_img(
        "input/images/a_returners_magic_should_be_special_6_1.jpg",
        ['input/audio/voice1.wav', 'input/audio/voice2.wav', 'input/audio/voice3.wav', 'input/audio/voice4.wav', 'input/audio/voice5.wav', 'input/audio/voice6.wav', 'input/audio/voice7.wav']
    )

    print("✅ Video generation complete")
    print(result)
