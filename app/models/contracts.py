from pydantic import BaseModel
from typing import List, Tuple

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
