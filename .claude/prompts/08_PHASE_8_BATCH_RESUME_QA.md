# Fase 8 — Robustez, batch noturno e QA

Melhore o AulaForge para rodar de madrugada em lote com segurança.

## Objetivo

Garantir que o pipeline completo não trave e gere relatório final útil.

## Implementar

- retries por etapa;
- `batch_report.md` completo;
- `batch_log.json` completo;
- status por aula;
- pular aulas processadas;
- continuar em caso de erro;
- comando `doctor` para verificar dependências;
- testes principais.

## Comando doctor

```powershell
aulaforge doctor
```

Deve verificar:

- Python;
- FFmpeg;
- Whisper;
- Ollama;
- modelo `qwen3:30b`;
- OCR engine;
- config;
- acesso ao output dir;
- Notion MCP quando habilitado.

## Critérios de aceite

- Um curso com vários vídeos roda sem interação manual.
- Falhas viram relatório, não travamento silencioso.
- O usuário consegue saber o que foi processado, pulado, falhou ou ficou com aviso.
