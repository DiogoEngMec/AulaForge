# Fase 7 — Arquivos para Claude Code, Codex, prompts, agentes e skills

Implemente a geração de arquivos derivados para uso futuro.

## Objetivo

Para cada aula, gerar arquivos Markdown que ajudem a transformar o conteúdo em implementação prática.

## Saídas por aula

```text
10_CLAUDE_CODE_CONTEXT.md
11_CODEX_CONTEXT.md
12_PROMPTS_PRONTOS.md
13_AGENTES_SUGERIDOS.md
14_SKILLS_SUGERIDAS.md
15_IDEIAS_DE_PROJETOS.md
16_IMPLEMENTATION_PLAN.md
```

## Regras

- Não criar arquivos diretamente em `.claude/agents/`.
- Apenas sugerir agentes.
- Apenas sugerir skills.
- Criar prompts prontos para copiar e colar.
- Separar implementação real de ideias futuras.

## Estrutura de CLAUDE_CODE_CONTEXT.md

```markdown
# Contexto para Claude Code

## Resumo técnico da aula

## Arquivos/conceitos citados

## Possíveis tarefas de implementação

## Prompt recomendado para Claude Code

## Cuidados e riscos
```

## Estrutura de CODEX_CONTEXT.md

```markdown
# Contexto para Codex

## Objetivo de implementação

## Arquivos prováveis

## Tarefas em sequência

## Critérios de aceite

## Testes sugeridos
```

## Critérios de aceite

- Arquivos gerados são úteis isoladamente.
- Prompts são específicos.
- Agentes sugeridos têm nome, objetivo e quando usar.
- Skills sugeridas têm objetivo e possível estrutura.
