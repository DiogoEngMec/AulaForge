# Fase 1 — Fundação CLI/config/scanner

Implemente apenas a fundação do AulaForge.

## Objetivo

Criar a estrutura inicial do projeto Python com CLI local capaz de:

1. carregar config YAML;
2. receber uma pasta de curso;
3. encontrar vídeos;
4. ordenar aulas pelo número no nome;
5. criar a estrutura inicial de output;
6. gerar um relatório simples.

## Não implementar ainda

- extração de áudio;
- Whisper;
- Ollama;
- OCR;
- Notion;
- geração avançada de Markdown.

## Arquivos esperados

Crie estrutura parecida com:

```text
aulaforge/
  __init__.py
  cli.py
  config.py
  scanner.py
  paths.py
  logging.py
  schemas.py
  utils.py

tests/
  test_scanner.py
  test_paths.py

config.example.yaml
pyproject.toml
README.md
```

## Comando esperado

```powershell
python -m aulaforge process-course "C:\Aulas\Curso Teste"
```

## Critérios de aceite

- Lista vídeos encontrados.
- Ordena `aula 2` antes de `aula 10`.
- Cria pasta `output/Nome do Curso/`.
- Cria subpastas por aula.
- Gera `batch_report.md` inicial.
- Não quebra se a pasta não tiver vídeos; deve avisar com clareza.

## Boas práticas

- Use pathlib.
- Use dataclasses ou Pydantic para modelos.
- Use Rich para logs bonitos.
- Escreva testes para ordenação.
