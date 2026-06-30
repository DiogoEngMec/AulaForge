# Erros e checkpoints — AulaForge

## Objetivo

Permitir que o AulaForge rode durante a madrugada sem travar pedindo intervenção manual.

## Regras

### 1. Erro em uma aula não para o curso inteiro

Se uma aula falhar, registrar erro e continuar próxima.

### 2. Etapas intermediárias devem ser salvas

Cada etapa salva seus arquivos antes da próxima começar.

### 3. Retries

Etapas com maior chance de falha devem tentar novamente:

- Ollama;
- Notion;
- OCR;
- transcrição.

### 4. Relatório final

Sempre gerar:

```text
batch_report.md
batch_log.json
```

Mesmo se houver erro.

## Arquivo processing_log.json

Exemplo:

```json
{
  "lesson": "aula_01_introducao",
  "status": "completed_with_warnings",
  "steps": {
    "audio": "completed",
    "transcription": "completed",
    "ocr": "completed_with_warnings",
    "merge": "completed",
    "notion": "completed"
  },
  "warnings": [
    "Código OCR com baixa confiança em 00:12:15"
  ],
  "errors": []
}
```

## ERROR.md

Se uma aula falhar, gerar:

```text
ERROR.md
```

Com:

- etapa que falhou;
- mensagem de erro;
- stack trace resumido;
- sugestão de retry;
- arquivos que foram gerados antes do erro.
