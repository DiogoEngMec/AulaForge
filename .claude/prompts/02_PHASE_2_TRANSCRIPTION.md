# Fase 2 — Áudio + Whisper local

Implemente apenas extração de áudio e transcrição local.

## Objetivo

Para cada vídeo detectado:

1. verificar se já foi processado;
2. extrair áudio com FFmpeg;
3. transcrever com Whisper local;
4. salvar transcrição bruta e timestamps;
5. dividir em blocos de 15 minutos.

## Pré-requisito

A Fase 1 já deve estar funcionando.

## Arquivos esperados por aula

```text
audio/audio.mp3
01_TRANSCRICAO_BRUTA.txt
02_TRANSCRICAO_COM_TIMESTAMPS.json
03_CHUNKS_15_MIN.json
source_info.json
processing_log.json
```

## Não implementar ainda

- OCR;
- Notion;
- geração de anotação com Ollama;
- merge áudio + vídeo.

## Critérios de aceite

- Com vídeo real curto, gera áudio.
- Gera transcrição.
- Gera timestamps.
- Divide corretamente em blocos de 15 minutos.
- Segunda execução pula aula se não mudou.
- `--force` reprocessa.

## Boas práticas

- Use subprocess para FFmpeg com tratamento de erro.
- Se FFmpeg não existir, mostrar mensagem útil.
- Se Whisper falhar, registrar erro e continuar próxima aula.
- Não interromper lote inteiro por uma aula.
