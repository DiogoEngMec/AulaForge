# Estratégia de transcrição — AulaForge

## Objetivo

Gerar uma transcrição fiel da aula usando Whisper local.

## Saídas obrigatórias

```text
01_TRANSCRICAO_BRUTA.txt
02_TRANSCRICAO_COM_TIMESTAMPS.json
03_TRANSCRICAO_LIMPA.md
03_CHUNKS_15_MIN.json
```

## Transcrição bruta

Deve preservar ao máximo o que foi falado.

Não deve virar resumo.

## Transcrição limpa

Pode corrigir:

- pontuação;
- quebras de parágrafo;
- vícios de fala excessivos;
- frases muito quebradas.

Mas não deve inventar informação.

## Chunking

Aulas divididas em blocos de 15 minutos.

Exemplo:

```text
00:00–15:00
15:00–30:00
30:00–45:00
45:00–60:00
```

## Idioma

Anotação final em português.
Termos técnicos em inglês devem ser preservados.

Exemplos:

- model
- view
- template
- queryset
- migration
- pipeline
- agent
- skill
- prompt

## Regra de fidelidade

Separar sempre:

1. conteúdo falado;
2. conteúdo visto na tela;
3. interpretação organizada;
4. insights da IA.
