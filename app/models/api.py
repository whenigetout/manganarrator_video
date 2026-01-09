from typing import List, Tuple
from pathlib import Path

import app.models.domain as D

class DialoguePreviewOut(D.PaddleDialogueLineResponse):
    """
    API view over a dialogue line.
    Inherits ALL domain fields:
    - id
    - image_id
    - speaker
    - gender
    - emotion
    - text
    - paddlebbox
    """

    # API-only / derived fields
    viewport_size: Tuple[int, int]
    scaled_image_size: Tuple[int, int]
    pan_offset: int
    crop_box: Tuple[int, int, int, int]
    bbox_y: int


class ImagePreviewOut(D.PaddleOCRImage):
    """
    API view over an OCR image.
    Inherits:
    - image_id
    - parsedDialogueLines (with paddlebbox)
    - paddleocr_result
    """

    # API-only helpers

    # UI-specific projection
    dialoguePreviews: List[DialoguePreviewOut]
