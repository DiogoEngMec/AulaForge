# AulaForge — Guia Rápido

Processe sua primeira aula em 5 passos.

---

## Passo 1 — Instalar

```powershell
# Criar ambiente virtual e instalar
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[transcription]"
```

Pré-requisitos externos:

- **FFmpeg** no PATH → [ffmpeg.org](https://ffmpeg.org/download.html)
- **Ollama** rodando com `qwen3:30b` → `ollama pull qwen3:30b`

---

## Passo 2 — Criar configuração

```powershell
Copy-Item CONFIG_EXAMPLE.yaml aulaforge.yaml
```

Para começar, edite apenas o modelo do Whisper (mais rápido para testes):

```yaml
transcription:
  model: "base"   # tiny = mais rápido | medium = melhor qualidade
```

> `aulaforge.yaml` é local e está no `.gitignore`. Não será commitado.

---

## Passo 3 — Organizar os vídeos

Coloque os vídeos do curso em uma pasta **fora do repositório**:

```
C:\Aulas\MeuCurso\
  Aula 01 - Introducao.mp4
  Aula 02 - Conceitos.mp4
  Aula 03 - Pratica.mkv
```

Formatos suportados: `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`

O AulaForge detecta o número da aula pelo nome do arquivo e ordena automaticamente.

---

## Passo 4 — Processar

```powershell
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml
```

Ao terminar, você verá no console:

```
MeuCurso: 5 etapa(s) concluída(s), 2 pulada(s), 0 com falha.
```

> Com `notion.enabled: false` e `ocr.enabled: false`, Notion e OCR aparecem como puladas. Isso é esperado.

Para reprocessar apenas aulas com falhas recentes:

```powershell
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml --resume
```

---

## Passo 5 — Ver os resultados

Abra a pasta `output/MeuCurso/`:

```
output/MeuCurso/
  batch_report.md              ← status e timing de cada aula
  COURSE_OVERVIEW.md           ← resumo executivo do curso
  COURSE_PROJECT_IDEAS.md      ← ideias de projetos
  COURSE_AGENTS.md             ← agentes sugeridos
  aula_01_introducao/
    09_ANOTACAO_NOTION.md      ← notas estruturadas (Ollama)
    10_CLAUDE_CODE_CONTEXT.md  ← contexto para Claude Code
    03_TRANSCRICAO_LIMPA.md    ← transcrição em blocos de 15 min
    processing_log.json        ← log de status por step
    ...
```

---

## (Opcional) Passo 6 — Sincronizar com Notion

1. Defina o token do Notion:

```powershell
$env:NOTION_TOKEN = "secret_xxxx..."
```

2. Habilite no `aulaforge.yaml`:

```yaml
notion:
  enabled: true
  auto_send: true
  database_name: "Aulas Processadas"
```

3. Reprocesse:

```powershell
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml
```

---

## Avisos normais

- `FP16 is not supported on CPU; using FP32 instead` — mensagem do Whisper em CPU, sem GPU. Normal, pode ignorar.

---

## Próximos passos

Consulte o [README.md](README.md) para:

- lista completa de outputs gerados;
- todos os modos de operação;
- troubleshooting detalhado;
- flags disponíveis (`--force`, `--resume`, `--config`);
- como rodar os testes.
