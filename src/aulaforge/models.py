"""Domain models for AulaForge."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Status(StrEnum):
    """Status values shared by source_info.json and processing_log.json."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    SKIPPED_UNCHANGED = "skipped_unchanged"


class SourceInfo(BaseModel):
    """Fingerprint of a lesson video, matching DATA_CONTRACTS.md's schema.

    `status` reflects only the foundation/indexing step (Phase 1). A lesson
    being "completed" here does not mean later pipeline phases (transcription,
    notes, OCR, Notion, ...) have run against it — see ProcessingLog for that.
    """

    video_path: str
    file_name: str
    file_size: int
    last_modified: datetime
    hash: str
    processed_at: datetime
    status: Status


class StepLogEntry(BaseModel):
    """Outcome of a single pipeline step (foundation, transcription, ...) for a lesson.

    `source_hash` is the video fingerprint (SourceInfo.hash) this step ran
    against, for steps that depend on it. It lets a later run detect that the
    video changed since this step last completed, without comparing
    timestamps between steps (which is fragile). None for steps that don't
    depend on the video fingerprint, and for entries written before this
    field existed (old logs stay valid since it's optional).
    """

    step: str
    status: Status
    started_at: datetime
    finished_at: datetime
    message: str | None = None
    source_hash: str | None = None


class ProcessingLog(BaseModel):
    """Per-lesson log accumulating one entry per pipeline step, across phases."""

    lesson: str
    steps: list[StepLogEntry] = Field(default_factory=list)

    def latest(self, step: str) -> StepLogEntry | None:
        matches = [entry for entry in self.steps if entry.step == step]
        return matches[-1] if matches else None


class TranscriptSegment(BaseModel):
    """One Whisper transcript segment, matching DATA_CONTRACTS.md's schema."""

    start: float
    end: float
    text: str


class Lesson(BaseModel):
    """A single lesson video discovered inside a course folder."""

    number: int | None
    title: str
    slug: str
    video_path: Path
    output_dir: Path


class Course(BaseModel):
    """A course folder containing one or more lessons."""

    name: str
    input_path: Path
    output_path: Path
    lessons: list[Lesson] = Field(default_factory=list)


class NotionLessonInfo(BaseModel):
    """Notion sync bookkeeping for a single lesson's toggle block."""

    toggle_block_id: str
    synced_hash: str


class NotionPageInfo(BaseModel):
    """Course-level record of the Notion page/blocks AulaForge owns.

    Persisted as NOTION_PAGE_INFO.json under the course output folder (one
    file per course, since the Notion page itself is one-per-course). Acts
    as the primary source of truth for IDs so reruns avoid duplicating the
    course page or any lesson's toggle block.
    """

    course_page_id: str
    course_page_url: str
    database_id: str
    lessons: dict[str, NotionLessonInfo] = Field(default_factory=dict)
