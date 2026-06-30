# Contratos de dados — AulaForge

Este documento define estruturas internas que devem ser mantidas estáveis.

## Course

```json
{
  "title": "Curso Django CRM",
  "source_path": "C:\\Aulas\\Curso Django CRM",
  "output_path": "output/Curso Django CRM",
  "lessons": [],
  "created_at": "2026-06-30T00:00:00",
  "processed_at": null
}
```

## Lesson

```json
{
  "lesson_number": 1,
  "title": "Introdução",
  "video_path": "C:\\Aulas\\Curso Django CRM\\aula 1 - introducao.mp4",
  "output_path": "output/Curso Django CRM/aula_01_introducao",
  "duration_seconds": 1234,
  "status": "pending"
}
```

## SourceInfo

```json
{
  "video_path": "C:\\Aulas\\Curso Django CRM\\aula 1 - introducao.mp4",
  "file_name": "aula 1 - introducao.mp4",
  "file_size": 123456789,
  "last_modified": "2026-06-30T01:20:00",
  "hash": "abc123",
  "processed_at": "2026-06-30T03:10:00",
  "status": "completed"
}
```

## TranscriptSegment

```json
{
  "start": 0.0,
  "end": 12.5,
  "text": "Agora vamos criar o model Pipeline..."
}
```

## LessonChunk

```json
{
  "chunk_number": 1,
  "start": 0,
  "end": 900,
  "transcript_segments": [],
  "ocr_items": []
}
```

## OCRItem

```json
{
  "timestamp": 735.2,
  "frame_path": "frames/00-12-15.png",
  "screen_type": "vscode",
  "raw_text": "class Pipeline(models.Model):",
  "clean_text": "class Pipeline(models.Model):",
  "content_type": "code",
  "confidence": "medium"
}
```

## DetectedCode

```json
{
  "timestamp": 735.2,
  "language": "python",
  "code": "class Pipeline(models.Model):\n    name = models.CharField(max_length=100)",
  "confidence": "medium",
  "source": "ocr",
  "warning": "Código extraído via OCR com confiança média. Pode exigir revisão manual."
}
```

## DetectedCommand

```json
{
  "timestamp": 830.1,
  "command": "python manage.py makemigrations",
  "shell": "powershell_or_bash",
  "confidence": "high"
}
```

## ProcessingStatus

Valores possíveis:

```text
pending
skipped_unchanged
processing
completed
completed_with_warnings
failed
```
