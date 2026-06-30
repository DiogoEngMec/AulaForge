# Data contracts

Use stable JSON/Markdown outputs so each step can resume.

## source_info.json

```json
{
  "video_path": "C:\\Aulas\\Curso\\aula 1.mp4",
  "file_name": "aula 1.mp4",
  "file_size": 123456789,
  "last_modified": "2026-06-30T01:20:00",
  "hash": "sha256...",
  "processed_at": "2026-06-30T03:10:00",
  "status": "completed"
}
```

## transcript segment

```json
{
  "start": 0.0,
  "end": 12.4,
  "text": "..."
}
```

## OCR frame result

```json
{
  "timestamp": "00:12:15",
  "frame_path": "frames/00-12-15.png",
  "screen_type": "vscode",
  "text": "...",
  "detected_code": "...",
  "confidence": "medium"
}
```
