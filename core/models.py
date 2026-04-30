from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Category(SQLModel, table=True):
    id:    Optional[int] = Field(default=None, primary_key=True)
    name:  str           = Field(index=True, unique=True)
    color: str           = Field(default="#1E90FF")


class Task(SQLModel, table=True):
    id:              Optional[int]      = Field(default=None, primary_key=True)
    title:           str
    description:     Optional[str]      = None
    category_id:     Optional[int]      = Field(default=None, foreign_key="category.id")
    priority:        str                = Field(default="normal")   # low|normal|high|urgent
    status:          str                = Field(default="todo")     # todo|in_progress|done
    created_at:      datetime           = Field(default_factory=datetime.now)
    updated_at:      datetime           = Field(default_factory=datetime.now)
    reminder_at:     Optional[datetime] = None
    reminder_fired:  bool               = Field(default=False)
    attachment_path: Optional[str]      = None   # premier fichier (compat)
    attachments:     Optional[str]      = None   # JSON liste de tous les fichiers
