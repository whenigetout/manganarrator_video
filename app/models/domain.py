from pydantic import BaseModel
from typing import List, Tuple
from pathlib import Path
import json

Point = Tuple[int, int]


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    poly: List[Point]
    matched_rec_text_index: int
    matched_rec_text_index_orig: int


class DialogueLine(BaseModel):
    id: int
    image_id: str
    image_file_name: str
    image_rel_path_from_root: str
    speaker: str
    gender: str
    emotion: str
    text: str
    paddle_bbox: BBox


class PaddleOCRResult(BaseModel):
    rec_texts: List[str]
    rec_polys: List[List[Point]]
    rec_boxes: List[List[int]]


class LLMResult(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    throughput: float


class OCRImageResult(BaseModel):
    image_file_name: str
    image_rel_path_from_root: str
    image_id: str
    run_id: str
    result: LLMResult
    parsed_dialogue: List[DialogueLine]
    image_width: int
    image_height: int
    paddleocr_result: PaddleOCRResult


class OCRRun(BaseModel):
    """
    Represents ONE ocr_output_with_bboxes.json file + its parsed content.
    """
    json_path: Path
    images: List[OCRImageResult]

    @classmethod
    def from_json_file(cls, path: Path) -> "OCRRun":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(
                f"OCR JSON must be a list, got {type(data)} in {path}"
            )
        return cls(
            json_path=path,
            images=[OCRImageResult.model_validate(x) for x in data],
        )
