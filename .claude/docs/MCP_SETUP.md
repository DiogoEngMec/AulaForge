# MCP Setup — AulaForge + Notion

## Objetivo

O AulaForge deve enviar automaticamente a página final do curso para o Notion usando MCP.

## Estratégia

A integração com Notion deve ficar isolada em um módulo próprio:

```text
aulaforge/notion/
  publisher.py
  blocks.py
  page_finder.py
  schemas.py
```

Assim, se o MCP ou a forma de chamar o Notion mudar, apenas esse módulo precisa ser ajustado.

## Comportamento esperado

Para cada curso:

1. procurar uma página existente pelo nome do curso;
2. se existir, atualizar;
3. se não existir, criar;
4. inserir/atualizar visão geral;
5. inserir cada aula como bloco recolhível;
6. não enviar transcrição bruta;
7. não enviar screenshots;
8. enviar códigos detectados com timestamp e aviso de confiança.

## Estrutura Notion desejada

```text
Página: Curso Django CRM

Visão Geral do Curso
Mapa das Aulas
Principais Conceitos
Projetos Possíveis
Agentes Sugeridos
Skills Sugeridas
Prompts Prontos

▸ Aula 1 — Introdução
▸ Aula 2 — Models e Banco
▸ Aula 3 — Kanban
```

## Database sugerida

Database: `Aulas Processadas`

Propriedades:

- Título
- Curso
- Categoria
- Tema principal
- Subtemas
- Duração total
- Quantidade de aulas
- Data de processamento
- Status
- Caminho local
- Tem OCR?
- Tem código detectado?
- Tem comandos detectados?
- Modelo LLM
- Processado por

## Boas práticas

- Criar payload intermediário em `COURSE_NOTION_PAGE.md` antes de publicar.
- Salvar `notion_payload.json` antes do envio.
- Registrar o ID da página Notion no `course_state.json`.
- Evitar duplicar aulas já publicadas.
- Atualizar blocos por aula usando um identificador persistente sempre que possível.

## Fallback

Se o Notion falhar:

- salvar tudo localmente;
- gerar `NOTION_UPLOAD_FAILED.md`;
- registrar erro no `batch_report.md`;
- continuar o restante do processamento.

## Prompt para Claude Code quando for implementar MCP

Use o arquivo:

```text
prompts/04_PHASE_4_NOTION_MCP.md
```
