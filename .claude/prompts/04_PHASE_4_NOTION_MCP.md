# Fase 4 — Notion via MCP

Implemente a publicação no Notion via MCP.

## Objetivo

Criar ou atualizar uma página do curso no Notion.

## Comportamento

1. Procurar página existente pelo nome do curso.
2. Se existir, atualizar.
3. Se não existir, criar.
4. Inserir visão geral do curso.
5. Inserir cada aula como bloco recolhível estilo Toggle Heading 1.
6. Não enviar transcrição bruta.
7. Não enviar screenshots.

## Entrada

- `09_ANOTACAO_NOTION.md`
- `COURSE_OVERVIEW.md`
- config Notion

## Saídas locais

```text
COURSE_NOTION_PAGE.md
notion_payload.json
course_state.json
```

## Regras

- Isolar todo código de Notion em `aulaforge/notion/`.
- Se Notion falhar, salvar local e continuar.
- Não duplicar página do curso.
- Não duplicar aula já publicada quando possível.

## Critérios de aceite

- Curso novo cria página.
- Curso existente atualiza página.
- Aula aparece em bloco recolhível.
- Falha no Notion não apaga arquivos locais.

## Observação

Antes de implementar, verifique no ambiente do Claude Code quais ferramentas MCP Notion estão disponíveis. Não assuma nomes de funções se o ambiente não expuser isso claramente.
