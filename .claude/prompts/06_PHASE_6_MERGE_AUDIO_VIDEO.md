# Fase 6 — Merge áudio + vídeo

Implemente a união entre transcrição e OCR por timestamp.

## Objetivo

Combinar o que foi falado com o que apareceu na tela.

## Entrada

- `02_TRANSCRICAO_COM_TIMESTAMPS.json`
- `03_CHUNKS_15_MIN.json`
- `04_OCR_TELA.json`
- `06_CODIGOS_DETECTADOS.md`
- `07_COMANDOS_TERMINAL.md`

## Saída

```text
08_MERGE_AUDIO_VIDEO.md
09_ANOTACAO_NOTION.md atualizado
```

## Regras

- Associar OCR ao bloco de 15 minutos correspondente.
- Quando código estiver perto de uma explicação, unir os dois.
- Não afirmar que código é perfeito se veio de OCR.
- Inserir aviso de confiança.

## Exemplo de saída

```markdown
## Model Pipeline

Em aproximadamente 00:12:10, a aula apresenta o model `Pipeline`.

Código visto na tela em 00:12:15:

```python
class Pipeline(models.Model):
    name = models.CharField(max_length=100)
```

> Aviso: código extraído via OCR com confiança média. Pode exigir revisão manual.
```

## Critérios de aceite

- A anotação final inclui código detectado.
- Cada código tem timestamp.
- Códigos de baixa confiança aparecem com aviso.
- Conteúdo visual e falado são separados quando não houver relação clara.
