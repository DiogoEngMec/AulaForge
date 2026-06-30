# Error handling and checkpoints

## Rules

- A failure in one lesson must not stop the entire course.
- Save `processing_log.json` per lesson.
- Save `batch_report.md` per course.
- Retry transient operations up to configured attempts.
- Use `source_info.json` to skip unchanged videos.
- Provide `--force` later to reprocess.

## Status values

- pending
- processing
- completed
- completed_with_warnings
- failed
- skipped_unchanged
