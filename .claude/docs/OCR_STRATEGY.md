# Estratégia OCR — AulaForge

## Objetivo

Capturar o que aparece no vídeo e que não está presente na transcrição de áudio, especialmente:

- código;
- comandos de terminal;
- nomes de arquivos;
- telas de VS Code;
- slides;
- documentação;
- GitHub;
- Notion.

## Estratégia inicial

1. Extrair frames a cada 5 segundos.
2. Comparar frames para evitar duplicados.
3. Rodar OCR local.
4. Limpar texto extraído.
5. Classificar tipo de conteúdo.
6. Detectar código/comandos.
7. Salvar screenshots localmente.
8. Enviar para o Notion apenas timestamp + texto/código extraído.

## Confiança

Classificar cada detecção como:

```text
high
medium
low
```

## Regra para código com baixa confiança

O código deve aparecer no Notion com aviso:

```markdown
> Aviso: código extraído via OCR com baixa confiança. Pode exigir revisão manual.
```

## Não enviar screenshots ao Notion

Screenshots ficam apenas em:

```text
frames/
```

## Heurísticas para código

Indícios de código:

- presença de `class`, `def`, `function`, `import`, `const`, `let`, `return`;
- indentação;
- chaves `{}`;
- parênteses frequentes;
- extensões como `.py`, `.js`, `.ts`, `.html`, `.css`;
- palavras como `models.py`, `views.py`, `urls.py`, `settings.py`.

## Heurísticas para terminal

Indícios de terminal:

- comandos começando com `python`, `npm`, `git`, `pip`, `cd`, `ls`, `dir`;
- prompts como `PS C:\`, `$`, `>`;
- saída de comandos.

## Limitação esperada

OCR de código pode errar:

- aspas;
- indentação;
- underscores;
- dois pontos;
- vírgulas;
- chaves;
- caracteres pequenos.

Por isso, o código detectado nunca deve ser tratado como 100% confiável sem validação.
