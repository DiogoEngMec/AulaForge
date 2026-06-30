# Pipeline

```text
Course folder
  ↓
Discover videos
  ↓
Sort lessons
  ↓
For each lesson:
  ↓
Create output folder
  ↓
Create/read source_info.json
  ↓
Skip if unchanged
  ↓
Extract audio
  ↓
Transcribe audio
  ↓
Chunk transcript into 15-minute blocks
  ↓
Extract frames
  ↓
OCR frames
  ↓
Detect code/terminal/screen type
  ↓
Merge transcript + OCR by timestamp
  ↓
Generate lesson note
  ↓
Generate Claude Code/Codex files
  ↓
Update Notion course page
  ↓
Generate course overview and batch report
```

Phase 1 implements only discovery, output structure, config, checkpoints and logging.
