from pathlib import Path
import json, re
from typing import List, Dict, Any, Tuple, Optional
from app.video_runner import VideoRunner
from app.config import VideoConfig
from typing import Optional
import subprocess, shlex
import app.models.domain as d
import app.models.api as a
import mn_contracts.ocr as o
import app.models.exceptions as ex

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

    def _collect_paths(
        self,
        run: o.OCRRun,
    ) -> List[Tuple[Path, List[Path]]]:
        """
        For each image in the OCR run, return:
        - absolute image path
        - list of dialogue audio paths (one per dialogue, ordered)
        """
        collected: List[Tuple[Path, List[Path]]] = []

        # for img in run.images:
        #     # ---- resolve image path ----
        #     image_path = (
        #         Path(str(self.config.input_root))
        #         / img.image_rel_path_from_root
        #         / img.image_file_name
        #     )

        #     # ---- resolve dialogue audio paths ----
        #     image_audio_root = (
        #         run.json_path.parent
        #         / f"{Path(img.image_file_name).stem}_jpg"
        #     )

        #     dialogue_audios: List[Path] = []

        #     for dlg in img.parsed_dialogue:
        #         dlg_dir = image_audio_root / f"dialogue__{dlg.id}"
        #         audio_path = self._latest_audio(dlg_dir)
        #         dialogue_audios.append(audio_path)

        #     collected.append((image_path, dialogue_audios))

        return collected

    def build_chapter(self, 
                      run: o.OCRRun, 
                      version: int,
                      *,
                      out_dir: Optional[Path] = None,
                      side_margin_px: Optional[int] = None,
                      verbose: Optional[bool] = None,
                      capture_stderr: Optional[bool] = None,
                      capture_stdout: Optional[bool] = None,
                      ) -> list[dict]:
        """Build one chapter video from OCR JSON + audios."""
        # ---- collect image + dialogue audio paths (unchanged helpers) ----
        res = []
        img_and_audio = self._collect_paths(run)
        base_out_dir = out_dir if out_dir else run.ocr_json_file.parent / "video_output"

        for img, (image_path, audio_files) in zip(run.images, img_and_audio):
            if not audio_files:
                raise FileNotFoundError(f"No dialogue audio files found for {run.json_path.name}")

            # ---- make pan plan from bboxes ----
            pan_plan = self._make_pan_plan(img)
            if len(pan_plan) != len(audio_files):
                print(f"[WARN] pan_plan({len(pan_plan)}) != audio_files({len(audio_files)}). "
                    "Will align by min length.")
                min_len = min(len(pan_plan), len(audio_files))
                pan_plan = pan_plan[:min_len]
                audio_files = audio_files[:min_len]

            # ---- optional pre/post-roll (silence) ----
            pre_s = float(getattr(self.config, "pre_roll_seconds", 0) or 0)
            post_s = float(getattr(self.config, "post_roll_seconds", 0) or 0)
            # build container folder name, if img file name is img001.jpg, the folder name will be img001_jpg
            p = Path(img.image_file_name)
            container_folder_name = f"{p.stem}_{p.suffix.lstrip('.')}"
            img_out_dir = base_out_dir / container_folder_name
            img_out_dir.mkdir(parents=True, exist_ok=True)

            def _make_silence(out_wav: Path, seconds: float, sr: int = 48000) -> Path:
                import subprocess, shlex
                out_wav.parent.mkdir(parents=True, exist_ok=True)
                # overwrite (-y) to avoid making silence3, silence4, etc.
                cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
                subprocess.run(shlex.split(cmd), check=True)
                return out_wav

            if pre_s > 0:
                pre_sil = img_out_dir / "silence_pre.wav"
                _make_silence(pre_sil, pre_s)
                audio_files = [pre_sil] + audio_files
                pan_plan = [{"dlg_id": -1, "offset": 0}] + pan_plan  # keep the camera at the top for preroll

            if post_s > 0:
                post_sil = img_out_dir / "silence_post.wav"
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
            existing = list(img_out_dir.glob("v*.mp4"))
            import re
            ver = 1 + max([int(m.group(1)) for f in existing if (m := re.search(r"v(\d+)", f.name))] or [0])
            out_file = img_out_dir / f"v{ver}.mp4"

            # ---- run the render (pass output_dir so video lands next to JSON) ----
            result = self.runner.run_single_img(
                image_path=image_path,
                audio_files=audio_files,
                out_filename=out_file.name,
                max_w=self.res_w,
                max_h=self.res_h,
                pan_plan=pan_plan,
                output_dir=img_out_dir,
                verbose=verbose,
                capture_stderr=capture_stderr,
                capture_stdout=capture_stdout
            )
            res.append(result)

        return res

    def build_chapter_from_previews(self, 
                      run: OCRRun, 
                      version: int,
                      settings: RenderConfig,
                      *,
                      out_dir: Optional[Path] = None,
                      ) -> list:
        """Build one chapter video from OCR JSON + audios."""
        # ---- collect image + dialogue audio paths (unchanged helpers) ----
        res = []
        img_and_audio = self._collect_paths(run)
        base_out_dir = out_dir if out_dir else run.json_path.parent / "video_output"

        for img, (image_path, audio_files) in zip(run.images, img_and_audio):
            if not audio_files:
                raise FileNotFoundError(f"No dialogue audio files found for {run.json_path.name}")

            # ---- make pan plan from bboxes ----
            imagePreview = self.build_dialogue_previews(
                img,
                settings,
                image_path
            )

            # ---- optional pre/post-roll (silence) ----
            pre_s = float(getattr(self.config, "pre_roll_seconds", 0) or 0)
            post_s = float(getattr(self.config, "post_roll_seconds", 0) or 0)
            # build container folder name, if img file name is img001.jpg, the folder name will be img001_jpg
            p = Path(img.image_file_name)
            container_folder_name = f"{p.stem}_{p.suffix.lstrip('.')}"
            img_out_dir = base_out_dir / container_folder_name
            img_out_dir.mkdir(parents=True, exist_ok=True)

            def _make_silence(out_wav: Path, seconds: float, sr: int = 48000) -> Path:
                import subprocess, shlex
                out_wav.parent.mkdir(parents=True, exist_ok=True)
                # overwrite (-y) to avoid making silence3, silence4, etc.
                cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
                subprocess.run(shlex.split(cmd), check=True)
                return out_wav

            if pre_s > 0:
                pre_sil = img_out_dir / "silence_pre.wav"
                _make_silence(pre_sil, pre_s)
                audio_files = [pre_sil] + audio_files
                pan_plan = [{"dlg_id": -1, "offset": 0}] + pan_plan  # keep the camera at the top for preroll

            if post_s > 0:
                post_sil = img_out_dir / "silence_post.wav"
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
            existing = list(img_out_dir.glob("v*.mp4"))
            import re
            ver = 1 + max([int(m.group(1)) for f in existing if (m := re.search(r"v(\d+)", f.name))] or [0])
            out_file = img_out_dir / f"v{ver}.mp4"

            # ---- run the render (pass output_dir so video lands next to JSON) ----
            result = self.runner.run_single_img(
                image_path=image_path,
                audio_files=audio_files,
                out_filename=out_file.name,
                max_w=self.res_w,
                max_h=self.res_h,
                pan_plan=pan_plan,
                output_dir=img_out_dir,
                verbose=settings.verbose,
                capture_stderr=settings.capture_stderr,
                capture_stdout=settings.capture_stdout
            )
            res.append(result)

        return res

    def build_run(
        self,
        run_id: str,
        *,
        side_margin_px: Optional[int] = None,
        verbose: Optional[bool] = None,
        capture_stderr: Optional[bool] = None,
        capture_stdout: Optional[bool] = None,
    ) -> List[List[dict]]:
        """Process all OCR runs under a run_id directory."""
        run_dir = Path(str(self.config.output_root)) / run_id
        json_files = list(run_dir.rglob("ocr_output_with_bboxes.json"))

        side_margin_px = (
            side_margin_px
            if side_margin_px is not None
            else (self.config.side_margin_px or 0)
        )

        results: List[List[dict]] = []

        for json_path in json_files:
            run = OCRRun.from_json_file(json_path)

            out_dir = run.json_path.parent / "video_output"
            out_dir.mkdir(exist_ok=True)

            # determine next version
            existing = list(out_dir.glob("v*.mp4"))
            version = 1 + max(
                (int(m.group(1)) for f in existing if (m := re.search(r"v(\d+)", f.name))),
                default=0,
            )

            results.append(
                self.build_chapter(
                    run,
                    version,
                    out_dir=out_dir,
                    side_margin_px=side_margin_px,
                    verbose=verbose,
                    capture_stderr=capture_stderr,
                    capture_stdout=capture_stdout,
                )
            )

        return results

    def build_dialogue_line_preview(
            self,
            dlg: o.DialogueLine,
            img_size: d.Size,
            frame_size: d.Size,
            img_scale: float,
            frame_top_padding: int = 0,
            prev_preview: Optional[d.DialogueLine_preview] = None
    ) -> d.DialogueLine_preview:
        """
        Compute DialogueLine preview for ocr img dialogue line
        """
        try:
            # error if invalid bbox 
            if dlg.original_bbox.y1 < 0 or dlg.original_bbox.y1 > img_size.h:
                raise ex.InvalidInputError(f"Invalid bbox for dlgId: {dlg.id} with text: {dlg.text}")

            bbox_scaled = dlg.original_bbox.scaled(img_scale)
            y1 = prev_preview.preview_frame.y1 if prev_preview else 0
            y1 -= frame_top_padding
            y2 = y1 + frame_size.h

            # bbox is inside the frame/viewport
            if y1 <= bbox_scaled.y1 and y2 >= bbox_scaled.y2:
                pass
            # bbox falls outside the frame/viewport
            else:
                y1 = bbox_scaled.y1 - frame_top_padding
                y2 = y1 + frame_size.h

            # edge case: last bbox is too close to the bottom
            if y2 > img_size.h * img_scale:
                y2 = img_size.h * img_scale
                y1 = y2 - frame_size.h

            preview = d.DialogueLine_preview(
                **dlg.model_dump(),
                preview_frame=d.Frame(
                    x1=0,
                    y1=int(y1),
                    x2=frame_size.w,
                    y2=int(y2),
                ),
            )

            return preview
        except:
            raise ex.PreviewError

    def build_ocrimg_preview(
        self,
        img: o.OCRImage,
        settings: d.RenderConfig,
    ) -> d.OCRImg_preview:
        """
        Compute preview frames for each dialogue in an image.
        Pure function: no IO, no ffmpeg.
        """
        try:
            img_w, img_h = img.image_info.image_width, img.image_info.image_height
            img_size = d.Size(
                w=img_w, 
                h=img_h
            )

            frame_size = d.Size(
                w=settings.viewport_w - 2 * settings.side_margin_px,
                h=settings.viewport_h
            )

            # scale image to viewport width (same as video logic)
            img_scale = frame_size.w / img_size.w

            dlg_previews: List[d.DialogueLine_preview] = []

            prev_preview = None
            for dlg in img.dialogue_lines:
                prev_preview = self.build_dialogue_line_preview(
                    dlg=dlg,
                    img_size=img_size,
                    frame_size=frame_size,
                    img_scale=img_scale,
                    frame_top_padding=settings.first_dialog_top_padding,
                    prev_preview=prev_preview
                )

                dlg_previews.append(prev_preview)

            result = d.OCRImg_preview(
                **img.model_dump(),
                frame_size=frame_size,
                side_margin_px=settings.side_margin_px,
                frame_padding_top=settings.first_dialog_top_padding,
                img_scale=img_scale,
                dialogue_lines=dlg_previews
            )

            return result
        except:
            raise ex.PreviewError