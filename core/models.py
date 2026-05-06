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
    priority:        str                = Field(default="normal")
    status:          str                = Field(default="todo")
    created_at:      datetime           = Field(default_factory=datetime.now)
    updated_at:      datetime           = Field(default_factory=datetime.now)
    reminder_at:     Optional[datetime] = None
    reminder_fired:  bool               = Field(default=False)
    attachment_path: Optional[str]      = None
    attachments:     Optional[str]      = None   # JSON liste fichiers


class SubTask(SQLModel, table=True):
    id:         Optional[int] = Field(default=None, primary_key=True)
    task_id:    int           = Field(foreign_key="task.id", index=True)
    title:      str
    done:       bool          = Field(default=False)
    position:   int           = Field(default=0)   # ordre d affichage
    created_at: datetime      = Field(default_factory=datetime.now)
