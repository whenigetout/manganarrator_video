from pathlib import Path
import json, re
from typing import List, Dict, Any, Tuple
from app.video_runner import VideoRunner
from app.config import VideoConfig
from typing import Optional
import subprocess, shlex




class ChapterVideoBuilder:
    def __init__(self, config: VideoConfig, resolution=(1080,1920), safe_margin=200):
        self.runner = VideoRunner(config)
        self.res_w, self.res_h = resolution
        self.safe_margin = safe_margin
        self.config = config

    def _make_silence(self, out_wav: Path, seconds: float, sr: int = 48000) -> Path:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
        subprocess.run(shlex.split(cmd), check=True)
        return out_wav

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

    def _make_pan_plan(self, json_file: Path) -> List[Dict[str, Any]]:
        """
        Compute a monotonic top->bottom pan plan using dialogue bboxes.
        - Starts slightly ABOVE the first dialogue (first_dialog_margin_pct of viewport height).
        - Uses *scaled* image height to clamp offsets (since we scale to self.res_w).
        - Ensures offset never decreases (monotonic pan).
        Returns: list of {"dlg_id": int, "offset": int}
        """
        data = json.loads(json_file.read_text(encoding="utf-8"))[0]
        raw_w = int(data["image_width"])
        raw_h = int(data["image_height"])

        # After we scale to viewport width (self.res_w), height scales proportionally
        scaled_h = int(raw_h * self.res_w / raw_w)
        max_offset = max(0, scaled_h - self.res_h)

        dialogs = [d for d in data["parsed_dialogue"] if d.get("paddle_bbox")]
        plan: List[Dict[str, Any]] = []

        cur_offset = 0
        first_margin_pct = getattr(self.config, "first_dialog_margin_pct", 0.02)
        try:
            first_margin_pct = float(first_margin_pct)
        except Exception:
            first_margin_pct = 0.02
        first_margin = int(self.res_h * first_margin_pct)


        for idx, dlg in enumerate(dialogs):
            y = int(dlg["paddle_bbox"]["y1"])
            # scale y to match the scaled image height
            y_scaled = int(y * self.res_w / raw_w)

            if idx == 0:
                # start a little above the first bubble
                offset = max(0, y_scaled - first_margin)
            else:
                # keep offset non-decreasing; aim to bring the next bubble into view
                if y_scaled < cur_offset:
                    offset = cur_offset
                else:
                    offset = max(0, y_scaled - self.safe_margin)

            # clamp to the scaled image height bottom
            offset = min(offset, max_offset)
            cur_offset = offset
            plan.append({"dlg_id": dlg["id"], "offset": offset})

        return plan

    def build_chapter(self, 
                      json_file: Path, 
                      version: int,
                      *,
                      side_margin_px: Optional[int] = None,
                      verbose: Optional[bool] = None,
                      capture_stderr: Optional[bool] = None,
                      capture_stdout: Optional[bool] = None,
                      ) -> dict:
        """Build one chapter video from OCR JSON + audios."""
        # ---- collect image + dialogue audio paths (unchanged helpers) ----
        image_path, audio_files = self._collect_paths(json_file)   # MUST return one file per dialogue, in order
        if not audio_files:
            raise FileNotFoundError(f"No dialogue audio files found for {json_file}")

        # ---- make pan plan from bboxes ----
        pan_plan = self._make_pan_plan(json_file)
        if len(pan_plan) != len(audio_files):
            print(f"[WARN] pan_plan({len(pan_plan)}) != audio_files({len(audio_files)}). "
                "Will align by min length.")
            min_len = min(len(pan_plan), len(audio_files))
            pan_plan = pan_plan[:min_len]
            audio_files = audio_files[:min_len]

        # ---- optional pre/post-roll (silence) ----
        pre_s = float(getattr(self.config, "pre_roll_seconds", 0) or 0)
        post_s = float(getattr(self.config, "post_roll_seconds", 0) or 0)
        out_dir = json_file.parent / "video_output"
        out_dir.mkdir(parents=True, exist_ok=True)

        def _make_silence(out_wav: Path, seconds: float, sr: int = 48000) -> Path:
            import subprocess, shlex
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            # overwrite (-y) to avoid making silence3, silence4, etc.
            cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
            subprocess.run(shlex.split(cmd), check=True)
            return out_wav

        if pre_s > 0:
            pre_sil = out_dir / "silence_pre.wav"
            _make_silence(pre_sil, pre_s)
            audio_files = [pre_sil] + audio_files
            pan_plan = [{"dlg_id": -1, "offset": 0}] + pan_plan  # keep the camera at the top for preroll

        if post_s > 0:
            post_sil = out_dir / "silence_post.wav"
            _make_silence(post_sil, post_s)
            audio_files = audio_files + [post_sil]
            if pan_plan:
                pan_plan = pan_plan + [{"dlg_id": -2, "offset": pan_plan[-1]["offset"]}]
            else:
                pan_plan = [{"dlg_id": -2, "offset": 0}]

        # ---- logging so you can see exactly what’s being used ----
        print("[AUDIO ORDER]")
        for i, ap in enumerate(audio_files):
            print(f"  {i:02d}: {Path(ap).name}")
        print("[PAN OFFSETS]")
        for i, pp in enumerate(pan_plan):
            print(f"  {i:02d}: offset={pp['offset']} (dlg_id={pp['dlg_id']})")

        # ---- versioned output filename in the same folder as the JSON ----
        existing = list(out_dir.glob("v*.mp4"))
        import re
        ver = 1 + max([int(m.group(1)) for f in existing if (m := re.search(r"v(\d+)", f.name))] or [0])
        out_file = out_dir / f"v{ver}.mp4"

        # ---- run the render (pass output_dir so video lands next to JSON) ----
        result = self.runner.run_single_img(
            image_path=image_path,
            audio_files=audio_files,
            out_filename=out_file.name,
            max_w=self.res_w,
            max_h=self.res_h,
            pan_plan=pan_plan,
            output_dir=out_dir,
            verbose=verbose,
            capture_stderr=capture_stderr,
            capture_stdout=capture_stdout
        )
        return result


    def build_run(self, 
                  run_id: str,
                  *,
                  side_margin_px: Optional[int] = None,
                  verbose: Optional[bool] = None,
                  capture_stderr: Optional[bool] = None,
                  capture_stdout: Optional[bool] = None,
                  ) -> List[dict]:
        """Find all OCR JSON files under run_id folder and process each."""
        run_dir = Path(self.config.output_root) / run_id
        json_files = list(run_dir.rglob("ocr_output_with_bboxes.json"))
        side_margin_px = side_margin_px if side_margin_px else self.config.side_margin_px
        if not side_margin_px:
            side_margin_px = 0

        results = []
        for jf in json_files:
            out_dir = jf.parent / "video_output"
            out_dir.mkdir(exist_ok=True)
            # determine next version number
            existing = list(out_dir.glob("v*.mp4"))
            version = 1 + max([int(re.search(r"v(\d+)", f.name).group(1)) for f in existing] or [0])
            results.append(self.build_chapter(jf, version, verbose=verbose, capture_stderr=capture_stderr, capture_stdout=capture_stdout, side_margin_px=side_margin_px))
        return results
