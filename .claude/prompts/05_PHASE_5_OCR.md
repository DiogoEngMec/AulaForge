# Fase 5 — OCR local do vídeo

Implemente OCR local do vídeo.

## Objetivo

Extrair informações visuais que a transcrição não captura.

## Entrada

- vídeo original referenciado em `source_info.json`

## Saídas

```text
frames/
04_OCR_TELA.json
05_OCR_TELA.md
06_CODIGOS_DETECTADOS.md
07_COMANDOS_TERMINAL.md
```

## Regras

- Extrair frames a cada 5 segundos inicialmente.
- Deduplicar frames semelhantes se possível.
- Salvar screenshots localmente.
- Não enviar screenshots ao Notion.
- Detectar possível código.
- Detectar possível terminal.
- Classificar confiança: high, medium, low.
- Código duvidoso deve aparecer com aviso.

## Não implementar ainda

- Merge final avançado com transcrição.

## Critérios de aceite

- Frames são salvos.
- OCR bruto é salvo.
- Possíveis códigos são extraídos.
- Possíveis comandos são extraídos.
- Erro no OCR não derruba pipeline inteiro.
