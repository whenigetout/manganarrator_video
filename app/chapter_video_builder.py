from pathlib import Path
import json, re
from typing import List, Dict, Any, Tuple
from app.video_runner import VideoRunner
from app.config import VideoConfig
from typing import Optional

class ChapterVideoBuilder:
    def __init__(self, config: VideoConfig, resolution=(1080,1920), safe_margin=200):
        self.runner = VideoRunner(config)
        self.res_w, self.res_h = resolution
        self.safe_margin = safe_margin
        self.config = config

    def _latest_audio(self, dlg_folder: Path) -> Path:
        """Pick latest vN file by sorting filenames like v1__, v2__, ..."""
        wavs = list(dlg_folder.glob("*.wav"))
        if not wavs:
            raise FileNotFoundError(f"No audio files in {dlg_folder}")
        # sort by version number in filename
        def vnum(p: Path):
            m = re.match(r"v(\d+)", p.name)
            return int(m.group(1)) if m else 0
        return max(wavs, key=vnum)

    def _collect_paths(self, json_file: Path) -> Tuple[Path, List[Path]]:
        """From OCR JSON → image path + audio files list."""
        data = json.loads(json_file.read_text())[0]
        run_id = data["run_id"]
        image_path = Path(self.config.input_root) / data["image_rel_path_from_root"] / data["image_file_name"]

        # Dialogue audio
        base_dir = json_file.parent / f"{Path(data['image_file_name']).stem}_jpg"
        audio_files = []
        for dlg in data["parsed_dialogue"]:
            dlg_folder = base_dir / f"dialogue__{dlg['id']}"
            audio_files.append(self._latest_audio(dlg_folder))
        return image_path, audio_files

    def _make_pan_plan(self, json_file: Path) -> List[Dict[str,Any]]:
        """Return viewport offsets for each dialogue."""
        data = json.loads(json_file.read_text())[0]
        plan = []
        cur_offset = 0
        for dlg in data["parsed_dialogue"]:
            bbox = dlg.get("paddle_bbox")
            if not bbox: 
                continue
            y = bbox["y1"]
            if y < cur_offset:  # already in frame
                offset = cur_offset
            else:
                offset = max(0, y - self.safe_margin)

            # --- clamp to scaled image height ---
            raw_w = data["image_width"]
            raw_h = data["image_height"]
            scaled_h = int(raw_h * self.res_w / raw_w)
            max_offset = max(0, scaled_h - self.res_h)
            offset = min(offset, max_offset)

            cur_offset = offset
            plan.append({"dlg_id": dlg["id"], "offset": offset})
        return plan


    def build_chapter(self, 
                      json_file: Path, 
                      version: int,
                      *,
                      verbose: Optional[bool] = None,
                      capture_stderr: Optional[bool] = None,
                      capture_stdout: Optional[bool] = None,
                      ) -> dict:
        """Build one chapter video from OCR JSON + audios."""
        image_path, audio_files = self._collect_paths(json_file)
        pan_plan = self._make_pan_plan(json_file)

        out_dir = json_file.parent / "video_output"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / f"v{version}.mp4"

        # Extend VideoRunner/FClip to accept crop offsets
        result = self.runner.run_single_img(
            image_path=image_path,
            audio_files=audio_files,
            out_filename=out_file.name,   # v{version}.mp4
            max_w=self.res_w,
            max_h=self.res_h,
            pan_plan=pan_plan,
            output_dir=out_dir,           # write next to the JSON, in the same folder
            verbose=verbose,
            capture_stderr=capture_stderr,
            capture_stdout=capture_stdout
        )

        return result

    def build_run(self, 
                  run_id: str,
                  *,
                  verbose: Optional[bool] = None,
                  capture_stderr: Optional[bool] = None,
                  capture_stdout: Optional[bool] = None,
                  ) -> List[dict]:
        """Find all OCR JSON files under run_id folder and process each."""
        run_dir = Path(self.config.output_root) / run_id
        json_files = list(run_dir.rglob("ocr_output_with_bboxes.json"))
        results = []
        for jf in json_files:
            out_dir = jf.parent / "video_output"
            out_dir.mkdir(exist_ok=True)
            # determine next version number
            existing = list(out_dir.glob("v*.mp4"))
            version = 1 + max([int(re.search(r"v(\d+)", f.name).group(1)) for f in existing] or [0])
            results.append(self.build_chapter(jf, version, verbose=verbose, capture_stderr=capture_stderr, capture_stdout=capture_stdout))
        return results
