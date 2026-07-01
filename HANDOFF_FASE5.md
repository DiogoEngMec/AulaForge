# HANDOFF — Fase 5: OCR local de vídeo

## Estado atual da master

`master` está em `b1b246c Implementa OCR local de vídeo`.
As Fases 1–5 estão completas e integradas. Working tree limpo.

---

## Fases implementadas

| Fase | Descrição | Status |
|---|---|---|
| 1 | Foundation: CLI, config, discovery, checkpoints | master ✅ |
| 2 | Transcrição: FFmpeg + Whisper local | master ✅ |
| 3 | Notas locais: Ollama / qwen3:30b | master ✅ |
| 4 | Sincronização com Notion via REST | master ✅ |
| 5 | OCR: extração de frames + detecção código/terminal | master ✅ (mergeada de `aulaforge/ocr`) |
| 6 | Merge áudio/vídeo: alinhamento de timelines | não iniciada |
| 7 | Outputs Claude Code / Codex | não iniciada |
| 8 | Batch robusto / QA / refactor | não iniciada |

---

## Branch da Fase 5

Desenvolvida em `aulaforge/ocr`, mergeada em `master`.
Commit de entrega: `b1b246c`

---

## Arquivos criados / alterados na Fase 5

### Novos

| Arquivo | Descrição |
|---|---|
| `src/aulaforge/video_frames.py` | Extração de frames via FFmpeg com promoção atômica de diretório Windows-safe |
| `src/aulaforge/ocr.py` | Pipeline OCR: pré-processamento, Tesseract, classificação de tela, dedup, 4 outputs atômicos |
| `tests/test_video_frames.py` | 19 testes (sem FFmpeg real) — extração, timestamps, atomicidade, limpeza de lixo |
| `tests/test_ocr.py` | ~35 testes (sem Tesseract real) — deps, hash, classificação, dedup, saves, writes |

### Modificados

| Arquivo | O que mudou |
|---|---|
| `src/aulaforge/models.py` | `OcrFrameResult` adicionado |
| `src/aulaforge/config.py` | `OcrConfig` + campo `ocr: OcrConfig` em `AulaForgeConfig` |
| `src/aulaforge/checkpoints.py` | `OCR_STEP`, `needs_ocr_processing`, `process_lesson_ocr`, `record_skipped_ocr`, `record_ocr_skipped_disabled` |
| `src/aulaforge/cli.py` | Bloco `--- Phase 5: OCR ---` após bloco Notion |
| `pyproject.toml` | Override mypy para `pytesseract.*`, `cv2.*`, `PIL.*`; extra `[ocr]` já existia |
| `CONFIG_EXAMPLE.yaml` | Seção `ocr:` completa e alinhada com `OcrConfig` |
| `tests/test_checkpoints.py` | +12 testes de checkpoint OCR |
| `tests/test_cli.py` | +5 testes de integração CLI OCR |
| `.claude/docs/DATA_CONTRACTS.md` | Campo `detected_commands` adicionado ao schema de `OcrFrameResult` |

### Artefatos locais gerados por run

```
output/<Curso>/<aula>/04_OCR_TELA.json           # list[OcrFrameResult] — fonte de verdade
output/<Curso>/<aula>/05_OCR_TELA.md             # resumo legível com timestamps e confiança
output/<Curso>/<aula>/06_CODIGOS_DETECTADOS.md   # blocos de código detectados
output/<Curso>/<aula>/07_COMANDOS_TERMINAL.md    # comandos de terminal detectados
output/<Curso>/<aula>/frames/HH-MM-SS.png        # frames retidos conforme política
output/<Curso>/<aula>/processing_log.json        # step "ocr" com source_hash
```

---

## Decisões importantes

| Decisão | Escolha |
|---|---|
| `ocr.enabled` padrão | `False` — OCR é opt-in (pode ser lento) |
| Nomeação de frames | FFmpeg gera `frame_%06d.png`; Python converte para `HH-MM-SS.png` (dashes, não colons) |
| Sem `-strftime` no FFmpeg | Timestamp calculado em Python: `(frame_num - 1) * interval_seconds` |
| Promoção de diretório no Windows | `frames.tmp/ → frames/` com backup `frames.old/`; `os.replace()` não funciona em dir não-vazio no Windows |
| Imports lazy | `pytesseract`, `Pillow`, `cv2` só importados dentro de funções — CLI importável sem `.[ocr]` |
| `cv2` opcional | Fallback para Pillow puro quando OpenCV não instalado |
| Dedup | `_text_change_count` ≥ `min_text_change_chars`; frames com código/comandos/terminal nunca descartados |
| Writes atômicos | `.tmp` + `os.replace()` para todos os 4 outputs por aula |
| Hash de checkpoint | `SHA256("ocr:v1:<video_hash>:<interval>:<lang>:<min_chars>:<save_local>:<preprocess>:<detect_code>:<detect_terminal>:<detect_screen_type>")` |
| Classificação de tela | Heurística por regex scoring: terminal > vscode > browser > slides (≥2 linhas curtas) > other |
| Frames ausente = reprocessar | `needs_ocr_processing` retorna True se `frames/` ausente e `save_screenshots_local=True` |
| Skip inteligente | Segunda execução sem mudanças não chama FFmpeg nem Tesseract |
| `batch_report.md` | Coluna `Ocr` aparece automaticamente via descoberta dinâmica de colunas |

---

## Dependências OCR

### Python (extra `[ocr]`)

```powershell
pip install "aulaforge[ocr]"
# Instala: pillow>=10.3.0, opencv-python>=4.10.0.84, pytesseract>=0.3.10
```

### Tesseract (binário Windows)

1. Baixe o instalador em https://github.com/UB-Mannheim/tesseract/wiki
   (ex: `tesseract-ocr-w64-setup-5.x.x.exe`)
2. Durante a instalação, marque os language packs **Portuguese** e **English**
3. Adicione o diretório ao PATH (ex: `C:\Program Files\Tesseract-OCR`)
4. Verifique: `tesseract --version` no terminal

> **Nota Windows:** defina `TESSDATA_PREFIX` se `tesseract --list-langs` retornar erro.
> O check de language packs é best-effort; a ausência da variável não aborta o OCR,
> apenas pula a verificação de pacotes de idioma.

### Configuração mínima para ativar OCR

```yaml
ocr:
  enabled: true
  lang: "por+eng"
  frame_interval_seconds: 5
```

---

## Status dos testes

```
pytest:  290 passed, 1 skipped  (1 skipped = Whisper real, esperado)
ruff:    All checks passed
mypy:    Success: no issues found in 17 source files
```

Todos os testes passam sem FFmpeg real, sem Tesseract real, sem `.[ocr]` instalado.

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| O1 | Baixa | `frame_path` em `OcrFrameResult` usa forward-slash (`"frames/00-00-00.png"`) para portabilidade JSON/Notion. Ao reconstruir o path real no Windows, usar `Path(frame_path)` que normaliza separadores. |
| O2 | Info | `send_screenshots_to_notion` e `show_low_confidence_code_in_notion` em `OcrConfig` são campos dormentes para integração futura Notion+OCR (Fase 6+). |
| O3 | Info | `classify_screen_type` não distingue `documentation`, `Notion` ou `GitHub` como mencionado em `OCR_STRATEGY.md`. Classificação básica suficiente para a Fase 5. |
| O4 | Baixa | Mock de `pytesseract` em `test_run_ocr` usa `builtins.__import__` — funciona, mas frágil a refactors. Candidato a migrar para `sys.modules` numa fase de QA. |

---

## Próxima fase recomendada

**Fase 6 — Merge áudio/vídeo**: alinhamento de timelines de transcrição e OCR para gerar uma linha do tempo unificada por aula.

Agente sugerido: `audio-video-merge-engineer`
Prompt de fase: `.claude/prompts/06_PHASE_6_MERGE.md` (a criar)

---

## Prompt para iniciar a Fase 6

```
Estou no projeto AulaForge. As Fases 1–5 estão implementadas e commitadas em master.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada nele.
3. HANDOFF_FASE5.md (raiz do projeto) para o contexto completo da Fase 5.

Depois apresente o plano da Fase 6 — merge de timeline áudio/vídeo
(escopo, decisões a confirmar, arquivos a criar/alterar)
e aguarde aprovação antes de implementar.

Restrições permanentes:
- Local-first: Whisper local, Ollama/qwen3:30b local, OCR local.
- Não adicione APIs pagas.
- Não altere arquivos .claude.
- Não implemente fases futuras além da 6.
- NOTION_TOKEN sempre via variável de ambiente.
- ocr.enabled permanece False por padrão (OCR é opt-in).
```
