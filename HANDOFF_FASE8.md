# HANDOFF — Fase 8: Batch Robusto / QA / Hardening

## Estado atual da branch

Branch: `aulaforge/hardening` — Fase 8 implementada, QA formal aprovado e commitada.  
Commit: `e7ae2d1 Implementa hardening batch robusto`  
Working tree: limpa (sem arquivos modificados ou não rastreados).  
Próximo passo: merge para `master`.

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
| 8 | Batch robusto / QA / hardening | `aulaforge/hardening` ✅ (aguardando merge) |

---

## Escopo entregue na Fase 8

| Item | Descrição |
|---|---|
| Retry com backoff | Transcription (Whisper) e notes (Ollama): até `processing.retry_attempts` tentativas com delay `2 × tentativa` segundos |
| Flag `--resume` | Reprocessa apenas aulas com pelo menos um step `FAILED` no `processing_log.json` |
| `reports.py` | Extração de `write_batch_summary` de `checkpoints.py`; relatório enriquecido com duração por step, totais e tempo médio por etapa |
| Fix B1 | Removido `cfg.enabled` do payload SHA256 de outputs — campo era sempre `True` quando o hash era calculado |
| Fix B2 | Adicionado `max_implementation_plan_chars` em `OutputsConfig`; truncamento opcional de `16_IMPLEMENTATION_PLAN.md` |

### Fora do escopo (explicitamente rejeitado)

- Retry em Notion, OCR, Merge ou Outputs
- Fix B3 (COURSE_OVERVIEW.md truncado — baixa prioridade)
- Novas fases de pipeline
- Empacotamento ou distribuição
- Alterações em `.claude/`
- Mudança no formato de `processing_log.json` ou `source_info.json`

---

## Arquivos criados na Fase 8

| Arquivo | Descrição |
|---|---|
| `src/aulaforge/reports.py` | `write_batch_summary`, `_duration_seconds`, `_cell`: geração de `batch_log.json` e `batch_report.md` com timing |
| `tests/test_reports.py` | 9 testes unitários: contrato JSON, duração por célula, totais, médias, exclusão de SKIPPED, colunas dinâmicas, entradas vazias |

---

## Arquivos modificados na Fase 8

| Arquivo | O que mudou |
|---|---|
| `src/aulaforge/config.py` | `OutputsConfig.max_implementation_plan_chars: int \| None = None` |
| `src/aulaforge/outputs.py` | B1: `cfg.enabled` removido do hash; B2: `_gen_implementation_plan` aceita `max_chars`, `build_lesson_outputs` passa o parâmetro |
| `src/aulaforge/checkpoints.py` | `write_batch_summary` removida (extraída para `reports.py`); `import json` removido; `process_lesson_outputs` passa `max_implementation_plan_chars` |
| `src/aulaforge/cli.py` | `import time`; `_RESUME_OPTION`; `_should_skip_with_resume`; parâmetro `resume` em `process_course`; loops de retry para transcription e notes; import de `write_batch_summary` migrado para `reports` |
| `CONFIG_EXAMPLE.yaml` | Seção `outputs`: `max_implementation_plan_chars: null  # null = sem limite; ex: 5000` |
| `tests/test_checkpoints.py` | Import atualizado: `from aulaforge.reports import write_batch_summary` |
| `tests/test_outputs.py` | `test_hash_config_affects_result`: usa `max_implementation_plan_chars=5000` em vez do `enabled=False` que B1 tornou irrelevante |
| `tests/test_cli.py` | 9 novos testes: 4 de `--resume` e 5 de retry (transcription + notes) |

---

## Retry — comportamento implementado

Aplicado somente a **transcription** (Whisper) e **notes** (Ollama). Nenhuma outra etapa tem retry.

```
para cada aula que precisa de transcription ou notes:
    para tentativa em range(1, retry_attempts + 1):
        tentar executar step
        se sucesso:
            registrar COMPLETED
            break
        se falha e tentativa < retry_attempts:
            logger.warning(...)
            time.sleep(2 * tentativa)   # backoff: 2s, 4s, 6s...
    se todas as tentativas falharam:
        registrar FAILED
        had_processing_failure = True
```

**Modelo Whisper:** carregado uma única vez por run (`if model is None: model = load_whisper_model(...)`) antes do loop de retry. Nunca recarregado entre tentativas.

**Check de Ollama:** lazy e cached (`if ollama_errors is None: ...`), idêntico ao padrão das Fases 2–7. Executado no máximo uma vez por run, antes de qualquer retry de notes.

**`retry_attempts`:** campo único `processing.retry_attempts` (default: `3`) — compartilhado entre transcription e notes. Não há controle granular por etapa nesta fase (ver Pendências, item P3).

---

## `--resume` — comportamento implementado

```
aulaforge process-course /caminho/do/curso --resume
```

| Situação | Comportamento |
|---|---|
| Sem `processing_log.json` | Processa normalmente (sem log = nunca processada) |
| Log existe, nenhum step FAILED | Aula pulada por `--resume` |
| Log existe, ao menos um step FAILED | Aula reprocessada normalmente |
| `--force` e `--resume` juntos | `--force` tem precedência; todas as aulas são reprocessadas |

**Implementação:** `_should_skip_with_resume(lesson_output_dir, lesson_slug) -> bool`  
Retorna `True` (pular) quando nenhuma entrada do log tem `status.value == "failed"`.  
Executada antes de qualquer outra lógica por aula.

> **Limitação documentada (M1):** Em runs com `--resume`, o `batch_report.md` gerado mostra
> apenas as aulas processadas naquela execução — não o estado histórico completo do curso.
> Uma run `--resume` que reprocessa 1 de 4 aulas produz um relatório com apenas 1 linha de
> tabela. O `batch_log.json` da run anterior (estado completo) permanece em disco e não é
> sobrescrito pela run parcial.

---

## `reports.py` — novo `batch_report.md`

### Responsabilidades

| Módulo | Responsável |
|---|---|
| `reports.py` | `batch_log.json` + `batch_report.md` |
| `checkpoints.py` | Removida `write_batch_summary` (extraída) |
| `cli.py` | Importa de `reports`; chama `write_batch_summary(course, entries)` |

### Formato de `batch_log.json` (contrato estável — sem timing)

```json
{
  "course": "Nome do Curso",
  "generated_at": "2026-07-01T14:00:00",
  "lessons": {
    "aula_01_introducao": {
      "foundation": "completed",
      "transcription": "skipped_unchanged",
      "notes": "completed"
    }
  }
}
```

### Formato de `batch_report.md` (humano-legível — inclui timing)

```markdown
# Batch report - Nome do Curso

Gerado em: 2026-07-01T14:00:00

| Aula | Foundation | Transcription | Notes |
|---|---|---|---|
| aula_01_introducao | completed (0.4s) | skipped_unchanged (0.0s) | completed (12.3s) |

**Resumo:** 2 concluída(s) · 3 pulada(s) · 0 com falha
**Tempo médio:** foundation: 0.4s · notes: 12.3s
```

**Colunas:** descobertas dinamicamente dos steps presentes — nenhuma mudança necessária para nova fase adicionar etapa.

**Média:** calculada apenas sobre steps `COMPLETED` e `FAILED`. Steps `SKIPPED_UNCHANGED` não distorcem a média.

---

## Fixes B1 e B2

### B1 — Hash de outputs

**Antes (Fase 7):**
```python
"config": {"enabled": cfg.enabled}  # sempre True quando o hash era computado
```

**Depois (Fase 8):**
```python
"config": {"max_implementation_plan_chars": cfg.max_implementation_plan_chars}
```

Efeito: segunda execução sem mudança de inputs ou config agora produz hash idêntico → `SKIPPED_UNCHANGED` correto.

---

### B2 — Limite de tamanho de `16_IMPLEMENTATION_PLAN.md`

Config (`aulaforge.yaml` ou `CONFIG_EXAMPLE.yaml`):

```yaml
outputs:
  max_implementation_plan_chars: null  # null = sem limite; ex: 5000 para limitar
```

Comportamento quando configurado:
1. `_gen_implementation_plan` gera o conteúdo completo normalmente.
2. Se `len(content) > max_chars`: trunca em `content[:max_chars].rstrip()`.
3. Appenda aviso: `_[Conteúdo truncado. Aumente max_implementation_plan_chars na config para ver o conteúdo completo.]_`

> **Limitação documentada (M2):** O truncamento ocorre no nível de caractere, não de linha ou
> bloco. Se `max_implementation_plan_chars` for muito baixo e o corte cair dentro de um bloco
> de código (` ``` `), o Markdown resultante terá uma cerca de código aberta sem fechar.
> O aviso de truncamento appended não fecha a cerca.
> **Recomendação:** usar valores ≥ 5000 caracteres. Para conteúdo curto típico (sem OCR intenso),
> o arquivo raramente ultrapassa 3000 caracteres.

---

## Status dos testes

```
pytest (suite completa):    446 passed, 1 skipped
  → tests/test_reports.py:     9 passed  (novos — Fase 8)
  → tests/test_cli.py:        30 passed  (+9 novos — resume + retry)
  → demais (Fases 1–7):      407 passed, 1 skipped  (sem regressão)

ruff check .:               All checks passed!
mypy src:                   Success: no issues found in 20 source files
```

O 1 skipped é o teste de Whisper real (marcado `pytest.mark.skip` desde a Fase 2 — comportamento esperado).

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| P1 | Baixa | **`--resume` report parcial (M1):** `batch_report.md` de run `--resume` mostra apenas aulas reprocessadas naquela run, não o histórico completo do curso. By-design; documentado acima. |
| P2 | Baixa | **Truncamento por caractere em B2 (M2):** `max_implementation_plan_chars` pode quebrar bloco Markdown se usado com valor muito baixo. Documentado acima. |
| P3 | Baixa | **`retry_attempts` compartilhado:** transcription e notes usam o mesmo `processing.retry_attempts`. Sem controle granular por etapa. |
| P4 | Baixa | **Sem feedback Rich no console para `--resume` skip:** lições puladas por `--resume` são registradas em `logger.info` (log file), não no console. O resumo final mostra "0 etapa(s) concluída(s)" o que pode parecer um run vazio para quem não consulta o log. |
| P5 | Baixa | **`_should_skip_with_resume` usa `.status.value`:** compara string `"failed"` em vez do mais idiomático `entry.status == Status.FAILED`. Funcional; refatoração cosmética. |
| B3 | Baixa | **`COURSE_OVERVIEW.md` truncado:** herdado da Fase 7 — mostra apenas a primeira linha do Resumo Executivo de cada aula. Resumos em lista com múltiplos itens ficam truncados. |

---

## Recomendação de teste real end-to-end

A Fase 8 não altera dependências externas. O teste real deve ser feito após o merge em `master`,
com um curso que tenha pelo menos uma aula com `09_ANOTACAO_NOTION.md` existente.

**Fluxo mínimo:**

```bash
# 1. Run completo (gera todos os steps)
aulaforge process-course "/caminho/Curso" --config aulaforge.yaml

# 2. Verificar batch_report.md com timing
cat output/Curso/batch_report.md

# 3. Segunda run: deve pular tudo (SKIPPED_UNCHANGED)
aulaforge process-course "/caminho/Curso" --config aulaforge.yaml
# Esperado: "0 etapa(s) concluída(s), N pulada(s), 0 com falha"

# 4. Simular falha e testar --resume
#    (editar processing_log.json de uma aula e trocar um status para "failed")
aulaforge process-course "/caminho/Curso" --config aulaforge.yaml --resume
# Esperado: apenas a aula modificada é reprocessada

# 5. Testar --force (ignora skip e --resume)
aulaforge process-course "/caminho/Curso" --config aulaforge.yaml --force
# Esperado: todas as aulas reprocessadas
```

**Verificar no `batch_report.md`:**
- Colunas aparecem automaticamente (discovery dinâmica)
- Células mostram `status (Xs)`
- Linha de totais e tempo médio presentes

---

## Próxima fase recomendada

**Fase 9 — Validação Real + Documentação do Usuário**

Com as Fases 1–8 cobrindo todo o pipeline técnico, a próxima prioridade é validar o
sistema com conteúdo real e torná-lo utilizável sem conhecimento do código-fonte:

| Candidato | Descrição |
|---|---|
| Teste real end-to-end completo | Processar 1 curso real com vídeos, Whisper e Ollama rodando; validar todos os outputs |
| `README.md` de usuário final | Instalação, configuração mínima (`aulaforge.yaml`), fluxo de uso passo a passo |
| CLI `--help` rico | Expandir textos de ajuda com exemplos por flag |
| Tratamento de B3 | Exibir resumo completo em `COURSE_OVERVIEW.md` (não apenas primeira linha) |
| Feedback Rich no `--resume` | Console mostra quais aulas foram puladas por `--resume` |

---

## Prompt para iniciar a Fase 9

```
Estou no projeto AulaForge, branch master (após merge da Fase 8).
As Fases 1–8 estão implementadas, testadas e commitadas.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada.
3. HANDOFF_FASE8.md na raiz do projeto.

Quero iniciar somente a próxima fase recomendada após a Fase 8.

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
