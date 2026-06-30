# Pipeline de processamento — AulaForge

## Pipeline por curso

```text
1. Ler config
2. Validar dependências
3. Encontrar vídeos
4. Ordenar aulas
5. Criar pasta output do curso
6. Para cada aula:
   6.1 Verificar se já foi processada
   6.2 Extrair áudio
   6.3 Transcrever
   6.4 Dividir em blocos de 15 minutos
   6.5 Fazer OCR, se habilitado
   6.6 Fazer merge áudio + vídeo
   6.7 Gerar anotação
   6.8 Gerar arquivos derivados
   6.9 Atualizar estado
7. Gerar visão geral do curso
8. Criar/atualizar Notion
9. Gerar relatório final
```

## Pipeline por aula

```text
video.mp4
  ↓
source_info.json
  ↓
audio.mp3
  ↓
transcript_raw.txt
  ↓
transcript_timestamps.json
  ↓
chunks_15_min.json
  ↓
ocr.json
  ↓
merge_audio_video.md
  ↓
anotacao_notion.md
  ↓
claude_code_context.md
  ↓
codex_context.md
  ↓
lesson_report.md
```

## Checkpoints

Cada etapa deve registrar status.

Exemplo:

```json
{
  "audio_extraction": "completed",
  "transcription": "completed",
  "ocr": "completed_with_warnings",
  "merge": "pending",
  "notion": "pending"
}
```

## Regras de continuação

- Se uma etapa já estiver concluída e o vídeo não mudou, não repetir.
- Se `--force`, repetir tudo.
- Se OCR falhar, continuar com transcrição.
- Se Notion falhar, salvar local e seguir.
- Se Ollama falhar, tentar novamente conforme config.
