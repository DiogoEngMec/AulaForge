# OCR strategy

## Goals

- Detect visible code that was not spoken.
- Detect terminal commands.
- Detect screen type: VS Code, terminal, browser, slides, documentation, Notion, GitHub.
- Save screenshots locally.
- Send only timestamp + extracted code/commands to Notion.

## Confidence

- High: readable and syntactically coherent.
- Medium: mostly readable but may need review.
- Low: include in Notion with warning and save local screenshot.

## Notion warning

> Aviso: trecho extraído por OCR com confiança baixa/média. Pode exigir revisão manual.
