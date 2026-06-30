# Stack técnica — AulaForge

## Linguagem

- Python 3.12+

## CLI

- Typer
- Rich

Motivo:

- Typer facilita comandos robustos.
- Rich melhora logs, tabelas e progresso no terminal.

## Configuração

- PyYAML
- Pydantic
- python-dotenv opcional

## Vídeo e áudio

- FFmpeg via subprocess
- pathlib
- hashlib

## Transcrição

- Whisper local já disponível no computador do usuário
- Alternativa futura: faster-whisper local, se fizer sentido

## OCR

Ferramentas candidatas:

- Tesseract OCR
- EasyOCR
- PaddleOCR

Decisão final deve ser tomada por teste prático.

Critérios:

- funcionar bem no Windows;
- ler código razoavelmente;
- aceitar screenshots de tela;
- não depender de API paga.

## Frames e vídeo

- OpenCV
- FFmpeg opcional para extração de frames

## IA local

- Ollama
- Modelo inicial: `qwen3:30b`

Usos:

- organização de conteúdo;
- resumo técnico;
- documentação;
- geração de prompts;
- geração de ideias;
- criação de arquivos para Claude Code e Codex.

## Notion

- Notion MCP via Claude Code

Observação:

A implementação deve isolar o publicador Notion em um módulo próprio. Assim, se a integração MCP mudar, o restante do sistema continua funcionando.

## Testes

- pytest

Testar primeiro:

- ordenação de aulas;
- criação de slugs;
- hash de arquivos;
- pular aulas já processadas;
- chunking de timestamps;
- geração de paths;
- parsing de config.

## Empacotamento futuro

Possíveis opções:

- `pyproject.toml`
- Poetry
- uv
- pipx

No início, manter simples.

## Hardware alvo inicial

- Windows
- 32 GB RAM
- AMD Ryzen 5 3600
- RX 5700 XT
- Ollama com `qwen3:30b`

## Observação de performance

O pipeline deve ser sequencial.

Motivo:

- modelo 30B é pesado;
- Whisper + OCR + LLM pode consumir muita RAM;
- processamento noturno precisa ser estável.
