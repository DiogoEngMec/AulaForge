# Fase 3 — Anotação local com Ollama

Implemente a geração local de anotações usando Ollama.

## Objetivo

Usar o modelo `qwen3:30b` para transformar a transcrição em uma anotação Markdown estruturada.

## Entrada

- `01_TRANSCRICAO_BRUTA.txt`
- `02_TRANSCRICAO_COM_TIMESTAMPS.json`
- `03_CHUNKS_15_MIN.json`

## Saídas

```text
03_TRANSCRICAO_LIMPA.md
09_ANOTACAO_NOTION.md
15_IDEIAS_DE_PROJETOS.md
processing_log.json atualizado
```

## Regras de conteúdo

- Escrever em português.
- Manter termos técnicos em inglês.
- Modo documentação/projeto.
- Não inventar conteúdo.
- Separar conteúdo da aula de insights da IA.

## Estrutura da anotação

```markdown
# Aula X — Título

## Resumo Executivo

## Ideia Central

## Índice com Timestamps

## Anotação Estruturada

## Conceitos Importantes

## Aplicações Práticas

## Insights da IA

## Ideias de Projeto
```

## Não implementar ainda

- Notion;
- OCR;
- merge áudio + vídeo;
- arquivos Claude/Codex completos.

## Critérios de aceite

- Funciona com Ollama local.
- Se Ollama não estiver rodando, erro claro.
- Gera Markdown legível.
- Mantém separação entre aula e insights.
- Usa blocos de 15 minutos para não lotar contexto.
