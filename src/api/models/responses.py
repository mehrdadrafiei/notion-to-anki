from typing import Dict, List, Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    message: Optional[str]
    details: Optional[Dict]


class FlashcardPreview(BaseModel):
    front: str
    back: str
    tags: List[str] = []


class TaskHistoryResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    per_page: int
