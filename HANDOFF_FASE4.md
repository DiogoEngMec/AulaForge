# HANDOFF — Fase 4: Sincronização com Notion

## Estado atual da master

`master` (local e `origin/master`) está em `f600ea5 Implementa sincronização com Notion`.
As Fases 1–4 estão completas e integradas. Working tree limpo.

---

## Fases implementadas

| Fase | Descrição | Branch / status |
|---|---|---|
| 1 | Foundation: CLI, config, discovery, checkpoints | master ✅ |
| 2 | Transcrição: FFmpeg + Whisper local | master ✅ |
| 3 | Notas locais: Ollama / qwen3:30b | master ✅ |
| 4 | Sincronização com Notion via REST | master ✅ (mergeada de `aulaforge/notion-mcp`) |
| 5 | OCR: extração de frames + detecção código/terminal | não iniciada |
| 6 | Merge áudio/vídeo: alinhamento de timelines | não iniciada |
| 7 | Outputs Claude Code / Codex | não iniciada |
| 8 | Batch robusto / QA / refactor | não iniciada |

---

## Branch da Fase 4

Desenvolvida em `aulaforge/notion-mcp`, mergeada em `master`.
Commit de entrega: `f600ea5`

---

## Arquivos criados / alterados na Fase 4

### Novos
| Arquivo | Descrição |
|---|---|
| `src/aulaforge/notion_client.py` | Cliente HTTP de baixo nível para a Notion REST API (httpx, retry, sem SDK) |
| `src/aulaforge/notion.py` | Lógica de negócio: `sync_lesson_to_notion`, `check_notion_dependencies`, `markdown_to_notion_blocks`, `can_skip_notion_without_network`, etc. |
| `tests/test_notion_client.py` | 20 testes do cliente HTTP (mocked) |
| `tests/test_notion.py` | 35 testes de lógica de negócio (mocked) |

### Modificados
| Arquivo | O que mudou |
|---|---|
| `src/aulaforge/config.py` | Classe `NotionConfig` adicionada |
| `src/aulaforge/models.py` | `NotionLessonInfo`, `NotionPageInfo` adicionados |
| `src/aulaforge/checkpoints.py` | `NOTION_STEP`, `needs_notion_processing`, `process_lesson_notion`, `can_skip_notion_without_network`, `record_*_notion` |
| `src/aulaforge/cli.py` | Bloco Fase 4 no loop de processamento |
| `tests/test_checkpoints.py` | +12 testes de checkpoint Notion |
| `tests/test_cli.py` | +6 testes de integração CLI Notion |
| `CONFIG_EXAMPLE.yaml` | Seção `notion:` com todos os campos documentados |

### Artefato local gerado por run
```
output/<Curso>/NOTION_PAGE_INFO.json     # IDs do Notion por curso/aula
output/<Curso>/<aula>/processing_log.json  # step "notion" com source_hash
```

---

## Decisões importantes

| Decisão | Escolha |
|---|---|
| Protocolo | REST direto com `httpx` (sem SDK Notion, sem MCP protocol) |
| Input | Só lê `09_ANOTACAO_NOTION.md`; transcrições/screenshots nunca enviados |
| Token | Via variável de ambiente (`NOTION_TOKEN`); nunca hardcoded |
| Um page por curso | Toggle Heading 1 por aula dentro da mesma page |
| Resolução de database | `database_id` explícito tem prioridade sobre `database_name` por busca |
| Hash de sincronização | `SHA256("v1:<database_id>:<note_content>")` — inclui versão, base e conteúdo |
| Skip inteligente (M1) | `can_skip_notion_without_network` evita HTTP quando tudo já está sincronizado |
| Segurança do toggle | Append-before-delete: novo conteúdo é adicionado antes de apagar o antigo |
| Limites da API | 2000 chars por rich_text; 100 blocos por request (com chunking automático) |
| Falha em aula isolada | `continue_on_error=True` por padrão; batch continua mesmo com falha pontual |

---

## Como configurar

### 1. Token Notion

```powershell
$env:NOTION_TOKEN = "secret_xxxxxxxxxxxxx"
```

Criar em: `notion.so/profile/integrations` → New integration → copiar token.

### 2. Compartilhar database com a integração

No Notion: abrir o database → `...` → Connections → selecionar sua integração.

### 3. Configuração mínima (`aulaforge.yaml`)

```yaml
notion:
  enabled: true
  database_name: "Aulas Processadas"   # ou use database_id abaixo
  # database_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # mais confiável
```

### 4. Rodar

```powershell
python -m aulaforge process-course "C:\Aulas\Meu Curso"
```

### Schema esperado no database Notion

O database deve ter as seguintes propriedades (nomes exatos):

| Propriedade | Tipo |
|---|---|
| `Name` | Title |
| `Pasta local` | Rich text |
| `Último processamento` | Date |

---

## Status dos testes

```
pytest:  197 passed, 1 skipped  (1 skipped = Whisper real, esperado)
ruff:    All checks passed
mypy:    Success: no issues found in 15 source files
```

---

## Pendências conhecidas

| ID | Prioridade | Descrição |
|---|---|---|
| B2 | Baixa | Nomes de propriedades do database (`Último processamento`, `Pasta local`) devem bater exatamente com o schema do Notion do usuário. Erros de nome causam 400 com mensagem clara. |
| B3 | Baixa | Se o usuário deletar a page de um curso no Notion, `NOTION_PAGE_INFO.json` ficará apontando para um ID inválido. Recovery: deletar `NOTION_PAGE_INFO.json` e rodar novamente. |
| B6-flag | Info | `lesson_blocks_as_toggle_h1: bool = True` está implementado e testado. Alterar para `false` cria toggles simples em vez de Heading 1 toggles. |

---

## Próxima fase recomendada

**Fase 5 — OCR**: extração de frames de vídeo, OCR local, detecção de código/terminal/slides.

Prompt: `.claude/prompts/05_PHASE_5_OCR.md`
Agente sugerido: `ocr-video-engineer`
Output esperado: `06_OCR_FRAMES/` com capturas e texto extraído por aula.

---

## Prompt para iniciar a Fase 5

```
Estou no projeto AulaForge. As Fases 1–4 estão implementadas e commitadas.

Leia primeiro:
1. .claude/docs/FILE_READING_ORDER.md
2. Os arquivos na ordem indicada nele.
3. .claude/prompts/05_PHASE_5_OCR.md

Depois apresente o plano da Fase 5 (escopo, decisões a confirmar, arquivos a criar/alterar)
e aguarde aprovação antes de implementar.

Restrições permanentes:
- Local-first: Whisper local, Ollama/qwen3:30b local, OCR local.
- Não adicione APIs pagas.
- Não altere arquivos .claude.
- Não implemente fases futuras.
- NOTION_TOKEN sempre via variável de ambiente.
```
