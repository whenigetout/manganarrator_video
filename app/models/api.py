from pydantic import BaseModel
from typing import List, Tuple

class DialoguePreviewOut(BaseModel):
    dialogue_id: int
    dialogue_text: str
    pan_offset: int
    crop_box: Tuple[int, int, int, int]
    bbox_y: int


class ImagePreviewOut(BaseModel):
    image_id: str
    image_file_name: str
    image_rel_path_from_root: str
    previews: List[DialoguePreviewOut]
