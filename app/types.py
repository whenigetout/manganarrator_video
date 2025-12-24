from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
import json
from pathlib import Path

Point = Tuple[int, int]


@dataclass(frozen=True)
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    poly: List[Point]
    matched_rec_text_index: int
    matched_rec_text_index_orig: int

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BBox":
        return cls(
            x1=d["x1"],
            y1=d["y1"],
            x2=d["x2"],
            y2=d["y2"],
            poly=[tuple(p) for p in d["poly"]],
            matched_rec_text_index=d["matched_rec_text_index"],
            matched_rec_text_index_orig=d["matched_rec_text_index_orig"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "poly": [list(p) for p in self.poly],
            "matched_rec_text_index": self.matched_rec_text_index,
            "matched_rec_text_index_orig": self.matched_rec_text_index_orig,
        }

@dataclass
class DialogueLine:
    id: int
    image_id: str
    image_file_name: str
    image_rel_path_from_root: str
    speaker: str
    gender: str
    emotion: str
    text: str
    paddle_bbox: BBox

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DialogueLine":
        return cls(
            id=d["id"],
            image_id=d["image_id"],
            image_file_name=d["image_file_name"],
            image_rel_path_from_root=d["image_rel_path_from_root"],
            speaker=d["speaker"],
            gender=d["gender"],
            emotion=d["emotion"],
            text=d["text"],
            paddle_bbox=BBox.from_dict(d["paddle_bbox"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "image_id": self.image_id,
            "image_file_name": self.image_file_name,
            "image_rel_path_from_root": self.image_rel_path_from_root,
            "speaker": self.speaker,
            "gender": self.gender,
            "emotion": self.emotion,
            "text": self.text,
            "paddle_bbox": self.paddle_bbox.to_dict(),
        }

@dataclass
class PaddleOCRResult:
    rec_texts: List[str]
    rec_polys: List[List[Point]]
    rec_boxes: List[List[int]]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PaddleOCRResult":
        return cls(
            rec_texts=d["rec_texts"],
            rec_polys=[[tuple(p) for p in poly] for poly in d["rec_polys"]],
            rec_boxes=d["rec_boxes"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rec_texts": self.rec_texts,
            "rec_polys": [[list(p) for p in poly] for poly in self.rec_polys],
            "rec_boxes": self.rec_boxes,
        }

@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    throughput: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LLMResult":
        return cls(
            text=d["text"],
            input_tokens=d["input_tokens"],
            output_tokens=d["output_tokens"],
            throughput=d["throughput"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "throughput": self.throughput,
        }

@dataclass
class OCRImageResult:
    image_file_name: str
    image_rel_path_from_root: str
    image_id: str
    run_id: str
    result: LLMResult
    parsed_dialogue: List[DialogueLine]
    image_width: int
    image_height: int
    paddleocr_result: PaddleOCRResult

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OCRImageResult":
        return cls(
            image_file_name=d["image_file_name"],
            image_rel_path_from_root=d["image_rel_path_from_root"],
            image_id=d["image_id"],
            run_id=d["run_id"],
            result=LLMResult.from_dict(d["result"]),
            parsed_dialogue=[
                DialogueLine.from_dict(x) for x in d["parsed_dialogue"]
            ],
            image_width=d["image_width"],
            image_height=d["image_height"],
            paddleocr_result=PaddleOCRResult.from_dict(d["paddleocr_result"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_file_name": self.image_file_name,
            "image_rel_path_from_root": self.image_rel_path_from_root,
            "image_id": self.image_id,
            "run_id": self.run_id,
            "result": self.result.to_dict(),
            "parsed_dialogue": [d.to_dict() for d in self.parsed_dialogue],
            "image_width": self.image_width,
            "image_height": self.image_height,
            "paddleocr_result": self.paddleocr_result.to_dict(),
        }

@dataclass
class OCRRun:
    """
    Represents ONE ocr_output_with_bboxes.json file + its parsed content.
    """
    json_path: Path
    images: List[OCRImageResult]

    @property
    def filename(self) -> str:
        return self.json_path.name

    @property
    def parent_dir(self) -> Path:
        return self.json_path.parent

    @classmethod
    def from_json_file(cls, path: Path) -> "OCRRun":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(
                f"OCR JSON must be a list, got {type(data)} in {path}"
            )
        return cls(
            json_path=path,
            images=[OCRImageResult.from_dict(x) for x in data],
        )

    def to_dict(self) -> List[Dict[str, Any]]:
        return [img.to_dict() for img in self.images]

@dataclass
class DialoguePreview:
    dialogue_id: int
    dialogue_text: str

    image_path: Path

    pan_offset: int
    viewport_size: Tuple[int, int]   # (width, height)
    scaled_image_size: Tuple[int, int]

    crop_box: Tuple[int, int, int, int]
    # (x1, y1, x2, y2) in scaled image coords

    bbox_y: int  # original bbox y1 (for debugging)
