# HANDOFF — Fase 7: Outputs Claude Code / Codex

## Estado atual da branch

Branch: `aulaforge/final-outputs` — Fase 7 implementada, QA formal aprovado.
Working tree possui arquivos novos/modificados prontos para commit.

---

## Fases implementadas

| Fase | Descrição | Status |
|---|---|---|
| 1 | Foundation: CLI, config, discovery, checkpoints | master ✅ |
| 2 | Transcrição: FFmpeg + Whisper local | master ✅ |
| 3 | Notas locais: Ollama / qwen3:30b | master ✅ |
| 4 | Sincronização com Notion via REST | master ✅ |
| 5 | OCR: extração de frames + detecção código/terminal | master ✅ |
| 6 | Merge áudio/vídeo: alinhamento de timelines | master ✅ |
| 7 | Outputs Claude Code / Codex | `aulaforge/final-outputs` ✅ (aguardando merge) |
| 8 | Batch robusto / QA / refactor | não iniciada |

---

## Branch da Fase 7

Desenvolvida em `aulaforge/final-outputs`.
Não mergeada em `master` ainda — este HANDOFF é gerado antes do merge.

---

## Escopo da Fase 7

Geração puramente local de artefatos de conhecimento estruturado a partir das
saídas já existentes das fases anteriores. **Sem chamadas a Whisper, FFmpeg,
Tesseract, Ollama ou Notion.** Toda geração é extração, reordenação e
reformatação de Markdown existente.

Inputs lidos (todos opcionais):
- `09_ANOTACAO_NOTION.md` — fonte primária de conteúdo estruturado (Fase 3)
- `08_MERGE_AUDIO_VIDEO.md` — contexto de código/timeline (Fase 6)
- `06_CODIGOS_DETECTADOS.md` — suplemento de código (Fase 5/OCR)
- `07_COMANDOS_TERMINAL.md` — suplemento de comandos (Fase 5/OCR)

Skip limpo (não é falha) quando **todos os 4 inputs estão ausentes**.

---

## Arquivos criados / alterados na Fase 7

### Novos

| Arquivo | Descrição |
|---|---|
| `src/aulaforge/outputs.py` | Módulo principal: extração de seções, geração dos 7 arquivos por aula, geração dos 5 arquivos por curso, hash de checkpoint, escrita atômica |
| `tests/test_outputs.py` | 69 testes (sem Whisper, Tesseract, FFmpeg, Ollama, Notion) |

### Modificados

| Arquivo | O que mudou |
|---|---|
| `src/aulaforge/config.py` | `OutputsConfig(enabled=True)` + campo `outputs: OutputsConfig` em `AulaForgeConfig` |
| `src/aulaforge/checkpoints.py` | `OUTPUTS_STEP`, `needs_outputs_processing`, `process_lesson_outputs`, `record_skipped_outputs`, `record_outputs_skipped_no_inputs`, `record_outputs_skipped_disabled` |
| `src/aulaforge/cli.py` | Bloco `--- Phase 7: Outputs ---` após bloco Phase 6; `write_course_outputs` pós-loop |
| `CONFIG_EXAMPLE.yaml` | Seção `outputs: enabled: true` |

---

## Outputs por aula (`output/<Curso>/<aula>/`)

| Arquivo | Conteúdo | Fonte principal |
|---|---|---|
| `10_CLAUDE_CODE_CONTEXT.md` | Contexto, objetivo, arquivos prováveis, agentes, cuidados, prompt sugerido | `09` + `08` + `06` + `07` |
| `11_CODEX_CONTEXT.md` | Tarefa, escopo, arquivos a criar/editar, critérios de aceite, testes esperados | `09` + `08` + `06` + `07` |
| `12_PROMPTS_PRONTOS.md` | Prompts extraídos de `## Prompts Prontos` | `09` |
| `13_AGENTES_SUGERIDOS.md` | Agentes extraídos de `## Agentes Sugeridos` | `09` |
| `14_SKILLS_SUGERIDAS.md` | Skills extraídas de `## Skills Sugeridas` | `09` |
| `15_IDEIAS_DE_PROJETOS.md` | Ideias extraídas de `## Ideias de Projeto` | `09` |
| `16_IMPLEMENTATION_PLAN.md` | Skeleton: objetivo, ideias, códigos detectados, comandos, próximos passos | `09` + `06` + `07` |

Todos os 7 arquivos incluem header de rastreabilidade (`> Fontes:`) listando
somente os inputs efetivamente presentes.

---

## Outputs por curso (`output/<Curso>/`)

| Arquivo | Conteúdo |
|---|---|
| `COURSE_OVERVIEW.md` | Índice do curso + primeiro parágrafo do Resumo Executivo de cada aula |
| `COURSE_PROJECT_IDEAS.md` | Ideias de projeto agregadas por aula |
| `COURSE_AGENTS.md` | Agentes sugeridos por aula |
| `COURSE_SKILLS.md` | Skills sugeridas por aula |
| `COURSE_PROMPTS.md` | Prompts prontos por aula |

Sempre regenerados após cada run (sem checkpoint). Filtrados pelas aulas com
step `outputs` em status `COMPLETED` ou `SKIPPED_UNCHANGED`.

---

## Decisões importantes

| Decisão | Escolha |
|---|---|
| `outputs.enabled` padrão | `True` — sem dependências externas, corre sempre por padrão |
| Nenhum LLM na Fase 7 | Fase 3 (Ollama) já gerou `09_ANOTACAO_NOTION.md`; Fase 7 apenas extrai e reformata |
| Skip limpo | Todos os 4 inputs ausentes → `record_outputs_skipped_no_inputs`; não é falha |
| Skip por `enabled=False` | `record_outputs_skipped_disabled`; verificado antes do hash |
| Hash de checkpoint | `SHA256(JSON{"version":"v1","config":{"enabled":true},"inputs":{...}})` com sentinelas `"no_notes"`/`"no_merge"`/`"no_codes"`/`"no_commands"` para None |
| Skip inteligente | Segunda execução sem mudanças nos 4 inputs pula sem reescrever os 7 arquivos |
| Escrita atômica | `.tmp` + `os.replace()` — Windows-safe |
| Rastreabilidade (M1) | `commands_raw` passado para `_sources_list()` nos geradores de arquivos 10 e 11; `07_COMANDOS_TERMINAL` aparece no `Fontes:` quando presente |
| Strip de header (M2) | `_strip_lesson_file_header()` skipa H1 + todas linhas `>` e em branco dinamicamente; sem número fixo de linhas |
| Matching de seções | `extract_section()` normaliza via NFKD + ASCII para matching diacritic-insensitive |
| Heading do curso | `_read_lesson_note_title()` lê H1 de `09_ANOTACAO_NOTION.md`; inclui número da aula para rastreabilidade; fallback: `lesson.title` |
| `16_IMPLEMENTATION_PLAN.md` | Skeleton sem LLM; contém todo o conteúdo de `06` e `07` bruto — revisão humana ou Fase 8 para enriquecer |
| Nenhuma dep externa nova | Fase 7 usa apenas stdlib Python (hashlib, json, os, re, unicodedata) |

---

## Status dos testes

```
pytest tests/test_outputs.py:   69 passed
pytest (suite completa):       428 passed, 1 skipped  (1 skipped = Whisper real, esperado)
ruff check .:                  All checks passed
mypy src (strict):             Success: no issues found in 19 source files
```

Todos os testes passam sem FFmpeg, Tesseract, Whisper, Ollama ou Notion reais.

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| B1 | Baixa | `cfg.enabled` incluído no payload do hash, mas é sempre `True` quando o hash é computado (o check de `enabled=False` no CLI ocorre antes). Campo redundante mas inofensivo; remover seria uma limpeza sem impacto funcional. |
| B2 | Baixa | `_gen_implementation_plan` insere o conteúdo bruto completo de `06` e `07` sem limite de tamanho. Para aulas com OCR intenso, `16_IMPLEMENTATION_PLAN.md` pode ficar muito longo. Monitorar quando OCR for amplamente usado. |
| B3 | Baixa | `COURSE_OVERVIEW.md` mostra apenas a primeira linha do Resumo Executivo de cada aula. Resumos em lista com múltiplos itens ficam truncados. Comportamento correto para leituras rápidas, mas pode omitir detalhes em resumos estruturados. |

---

## Recomendação para teste com dados reais

A Fase 7 não tem dependências pesadas e pode ser testada imediatamente após o
commit, sem Whisper, Ollama, Tesseract ou FFmpeg:

**Pré-requisito mínimo:** uma aula com `09_ANOTACAO_NOTION.md` já gerado
pela Fase 3.

**Fluxo de teste:**

```bash
# Roda somente a Fase 7 (fases anteriores já foram executadas)
aulaforge run --course "NomeDoCurso"

# Verifica os 7 arquivos gerados por aula
ls output/NomeDoCurso/aula_01/

# Verifica os 5 arquivos de curso
ls output/NomeDoCurso/

# Segunda execução: deve pular (SKIPPED_UNCHANGED) sem reescrever
aulaforge run --course "NomeDoCurso"
```

**Verificar no `batch_report.md`:** a coluna `Outputs` deve aparecer
automaticamente (descoberta dinâmica de colunas já existente no CLI).

---

## Próxima fase recomendada

**Fase 8 — Batch robusto / QA / hardening**: robustez de produção,
retry inteligente, relatórios mais detalhados, limpeza de code debt acumulado.

Candidatos para a Fase 8:
- Retry com backoff para etapas que falham por timeout (Whisper, Ollama)
- `--resume` que reprocessa somente aulas com step FAILED
- Relatório de batch com estatísticas por etapa (tempo médio, taxa de skip)
- Remoção do `cfg.enabled` redundante do hash de checkpoint (B1)
- Opção de limitar tamanho de `16_IMPLEMENTATION_PLAN.md` (B2)

---

## Prompt para iniciar a Fase 8

```
Estou no projeto AulaForge. As Fases 1–7 estão implementadas e commitadas em master.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada nele.
3. HANDOFF_FASE7.md (raiz do projeto) para o contexto completo da Fase 7.

Depois apresente o plano da Fase 8 — batch robusto / QA / hardening
(escopo, arquivos a criar/alterar, decisões a confirmar)
e aguarde aprovação antes de implementar.

Restrições permanentes:
- Local-first: Whisper local, Ollama/qwen3:30b local, OCR local.
- Não adicione APIs pagas.
- Não altere arquivos .claude.
- NOTION_TOKEN sempre via variável de ambiente.
- ocr.enabled permanece False por padrão (OCR é opt-in).
- merge.enabled permanece True por padrão (sem dependências externas).
- outputs.enabled permanece True por padrão (sem dependências externas).
```
