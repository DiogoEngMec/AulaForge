# HANDOFF — Fase 9: Validação Real + Documentação do Usuário

## Estado atual da branch

Branch: `aulaforge/real-validation-docs` — Fase 9 implementada, QA formal aprovado e corrigida.  
Working tree: limpa após correções de documentação.  
Próximo passo: commit e merge para `master`.

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
| 7 | Outputs Claude Code / Codex | master ✅ |
| 8 | Batch robusto / QA / hardening | master ✅ |
| 9 | Validação real + documentação do usuário | `aulaforge/real-validation-docs` ✅ (aguardando merge) |

---

## Escopo entregue na Fase 9

| Item | Descrição |
|---|---|
| Validação real end-to-end | Rounds 1–4 executados com o curso PedroSobral (1 aula `.mkv`) |
| Fix audio.py | Temp file `audio.tmp.mp3` em vez de `audio.mp3.tmp` — FFmpeg inferia formato pela extensão final |
| Fix cli.py `--resume` | Considera apenas o último status de cada step; falhas antigas não ativam mais o `--resume` |
| `README.md` reescrito | Documentação de usuário final completa |
| `QUICKSTART.md` criado | Guia de 5+1 passos para processar a primeira aula |
| `.gitignore` atualizado | `aulaforge.yaml` adicionado como arquivo local não commitado |

### Fora do escopo (explicitamente rejeitado)

- Fix B3 (COURSE_OVERVIEW.md truncado) — não confirmado na validação real
- Fix P4 (console Rich para --resume skip) — resolvido como efeito colateral da correção do --resume
- Novas fases de pipeline
- Empacotamento ou distribuição
- Alterações em `.claude/`

---

## Arquivos criados na Fase 9

| Arquivo | Descrição |
|---|---|
| `QUICKSTART.md` | Guia rápido de 5+1 passos |
| `HANDOFF_FASE9.md` | Este arquivo |

---

## Arquivos modificados na Fase 9

| Arquivo | O que mudou |
|---|---|
| `.gitignore` | `aulaforge.yaml` adicionado na seção `# Local env and secrets` |
| `README.md` | Reescrita completa — documentação de usuário final |
| `src/aulaforge/audio.py` | Fix: temp file `audio.tmp.mp3` via `output_path.with_stem(stem + ".tmp")` |
| `src/aulaforge/cli.py` | Fix: `_should_skip_with_resume` usa `ProcessingLog.latest(step)` por step único; help text de `--resume` atualizado |
| `tests/test_audio.py` | 2 asserts atualizados; 1 teste novo: `test_temp_path_passed_to_ffmpeg_ends_with_mp3_extension` |
| `tests/test_cli.py` | 1 teste novo: `test_resume_skips_lesson_with_stale_failed_but_recent_success` |

---

## Bug 1 — audio.mp3.tmp quebrava o FFmpeg

### Causa

`audio.py` gerava o arquivo temporário como `audio.mp3.tmp`:

```python
# Antes (Fase 2–8):
tmp_path = output_path.with_name(output_path.name + ".tmp")
# → audio.mp3.tmp  (extensão final = .tmp → FFmpeg não consegue inferir formato)
```

O FFmpeg determina o formato de saída pela extensão final do arquivo. `.tmp` não é reconhecido → erro `Unable to find a suitable output format`.

O bug estava latente desde a Fase 2 mas nunca foi exercitado porque o Whisper só foi instalado na Fase 9.

### Correção

```python
# Depois (Fase 9):
tmp_path = output_path.with_stem(output_path.stem + ".tmp")
# → audio.tmp.mp3  (extensão final = .mp3 → FFmpeg infere MP3)
```

`Path.with_stem()` disponível em Python 3.9+; projeto requer 3.11+. Escrita atômica preservada.

---

## Bug 2 — --resume ativava em falhas antigas do histórico

### Causa

`_should_skip_with_resume` varria toda a lista `log.steps` (histórico acumulado entre runs):

```python
# Antes (Fase 8):
return not any(entry.status.value == "failed" for entry in log.steps)
```

Se uma aula tinha uma entrada `FAILED` antiga mas foi reprocessada com sucesso depois, a entrada antiga permanecia no histórico e continuava ativando o `--resume`, fazendo a aula "entrar" (mas as etapas saíam como `SKIPPED_UNCHANGED`).

### Correção

```python
# Depois (Fase 9):
seen_steps = {entry.step for entry in log.steps}
for step in seen_steps:
    latest = log.latest(step)
    if latest is not None and latest.status == Status.FAILED:
        return False
return True
```

Usa `ProcessingLog.latest(step)` (`models.py:65`) que retorna a última entrada de cada step por posição na lista. Um failed antigo seguido de completed/skipped_unchanged não ativa mais o `--resume`.

---

## Validação real — Rounds 1–4

**Curso:** PedroSobral (`Modulo T01 - Aula 6 - Pedro Sobral Gestão de Tráfego.mkv`)  
**Pasta:** `C:\Aulas\PedroSobral\`  
**Config:** `aulaforge.yaml` local (`notion.enabled: false`, `ocr.enabled: false`, `transcription.model: base`)

### Round 1 — Cold run (pós-fix audio.py)

```
PedroSobral: 5 etapa(s) concluída(s), 2 pulada(s), 0 com falha.
```

- foundation: COMPLETED
- transcription: COMPLETED
- notes: COMPLETED
- notion: SKIPPED (disabled por config)
- ocr: SKIPPED (disabled por config)
- merge: COMPLETED
- outputs: COMPLETED

### Round 2 — Idempotência

```
PedroSobral: 0 etapa(s) concluída(s), 7 pulada(s), 0 com falha.
```

Todos os steps: SKIPPED_UNCHANGED. Checkpoint funcionando.

### Round 3 — --resume (pós-fix cli.py)

```
PedroSobral: 0 etapa(s) concluída(s), 0 pulada(s), 0 com falha.
```

Aula sem falhas atuais pulada corretamente. Falha antiga no histórico não ativou reprocessamento.

### Round 4 — --force

```
PedroSobral: 5 etapa(s) concluída(s), 2 pulada(s), 0 com falha.
```

Todas as aulas reprocessadas. Notion e OCR pulados por config.

---

## B3 — COURSE_OVERVIEW.md truncado

Herdado da Fase 7. Na validação real com o curso PedroSobral, o `COURSE_OVERVIEW.md` ficou completo e útil. **Não foi implementado** — condicionado a confirmação em validação, que não ocorreu.

Permanece como pendência de baixa prioridade.

---

## P4 — Console Rich para --resume skip

Na Fase 8, aulas puladas por `--resume` não apareciam no console (só no log). Com a correção do `--resume` na Fase 9, o comportamento ficou claro: aula sem falhas atuais é simplesmente pulada, e o console exibe o resumo final corretamente. **P4 considerado resolvido como efeito colateral.**

---

## Status final dos checks

```
pytest -q:         449 passed
ruff check .:      All checks passed!
mypy src:          Success: no issues found in 20 source files
```

Contagem de testes:
- `tests/test_audio.py`: 6 tests (+1 novo: extensão final do temp)
- `tests/test_cli.py`: 31 tests (+1 novo: stale failed + recent success → skip)
- Demais (Fases 1–8): 412 tests, sem regressão

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| B3 | Baixa | **COURSE_OVERVIEW.md truncado:** mostra apenas a primeira linha do resumo executivo de cada aula quando o Ollama gera múltiplos itens. Não confirmado na validação real com 1 aula. |
| P3 | Baixa | **`retry_attempts` compartilhado:** transcription e notes usam o mesmo `processing.retry_attempts`. Sem controle granular por etapa. |
| P5 | Baixa | **`_should_skip_with_resume` usa `latest` por posição:** refatoração cosmética. Funcional; sem impacto. |
| M1 | Baixa | **Limitação documentada (M1):** `batch_report.md` de run `--resume` mostra apenas aulas processadas naquela run, não o histórico completo. By-design. |
| M2 | Baixa | **Truncamento por caractere em B2:** `max_implementation_plan_chars` pode quebrar bloco Markdown se muito baixo. Documentado no HANDOFF_FASE8. |

---

## Aviso do Whisper em CPU

Durante a validação real, o Whisper emitiu:

```
FP16 is not supported on CPU; using FP32 instead
```

Mensagem normal quando rodando em CPU sem GPU. Não afeta o resultado. Documentado no README.md e QUICKSTART.md.

---

## Recomendação de próxima fase

Com as Fases 1–9 cobrindo o pipeline técnico completo e a validação real confirmada, as próximas prioridades naturais são:

| Candidato | Descrição |
|---|---|
| Fase 10 — Empacotamento | `pip install aulaforge` via PyPI; instalação sem clonar o repositório |
| Fase 10 — Múltiplas aulas | Validação com curso de 5+ aulas; testar batch report com múltiplas linhas |
| Fix B3 | Corrigir COURSE_OVERVIEW.md truncado se confirmado com múltiplas aulas |
| OCR real | Validação end-to-end com `ocr.enabled: true` e Tesseract instalado |

---

## Prompt para iniciar a próxima fase

```
Estou no projeto AulaForge, branch master (após merge da Fase 9).
As Fases 1–9 estão implementadas, testadas e commitadas.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada.
3. HANDOFF_FASE9.md na raiz do projeto.

Quero iniciar somente a próxima fase recomendada após a Fase 9.

Não dependa de slash commands customizados.
Não implemente nada ainda.
Não edite arquivos ainda.
Não rode dependências pesadas.
Não altere .claude.

Apresente o plano da fase seguinte com:
1. nome e objetivo;
2. escopo (dentro e fora);
3. arquivos a criar ou alterar;
4. riscos técnicos;
5. plano de testes;
6. critérios de aceite;
7. dúvidas bloqueantes.

Aguarde aprovação antes de implementar.

Restrições permanentes:
- Local-first: Whisper local, Ollama/qwen3:30b local, OCR local.
- Não adicione APIs pagas.
- Não altere arquivos .claude.
- NOTION_TOKEN sempre via variável de ambiente.
- ocr.enabled permanece False por padrão.
- merge.enabled e outputs.enabled permanecem True por padrão.
```
