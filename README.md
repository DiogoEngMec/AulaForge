# AulaForge

AulaForge é uma ferramenta de linha de comando, local-first, que transforma aulas gravadas em vídeo em uma base de conhecimento estruturada.

Dada uma pasta de curso com arquivos de vídeo, o AulaForge:

- extrai o áudio e transcreve com **Whisper local**;
- organiza o conteúdo em notas estruturadas com **Ollama + qwen3:30b**;
- extrai frames e detecta código/terminal com **OCR local** (opcional);
- integra transcrição e OCR em uma linha do tempo unificada;
- gera arquivos de contexto prontos para uso no **Claude Code** e **Codex**;
- sincroniza as notas com uma página do **Notion** (opcional);
- gera relatório de batch por curso.

Todo o processamento pesado (transcrição, notas, OCR) é local. Nenhuma API paga é usada.

---

## Requisitos

| Componente | Versão mínima | Obrigatório |
|---|---|---|
| Python | 3.11+ | Sim |
| FFmpeg | qualquer | Sim |
| openai-whisper | qualquer | Sim (transcrição) |
| Ollama | qualquer | Sim (notas) |
| Modelo qwen3:30b | — | Sim (notas) |
| Tesseract OCR | 4+ | Não (OCR opt-in) |
| Token do Notion | — | Não (Notion opt-in) |

### Formatos de vídeo suportados

`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`

---

## Instalação

```powershell
# 1. Clonar o repositório
git clone <url-do-repositório>
cd AulaForge

# 2. Criar ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Instalar dependências básicas + Whisper
pip install -e ".[transcription]"

# 4. (Opcional) Instalar dependências de OCR
pip install -e ".[ocr]"

# 5. (Opcional) Instalar dependências de desenvolvimento
pip install -e ".[dev]"
```

### FFmpeg

Baixe em [ffmpeg.org](https://ffmpeg.org/download.html) e adicione ao PATH do sistema.

Verifique com:

```powershell
ffmpeg -version
```

### Ollama + qwen3:30b

Instale o Ollama em [ollama.com](https://ollama.com) e baixe o modelo:

```powershell
ollama pull qwen3:30b
```

Verifique com:

```powershell
ollama list
```

---

## Configuração

Copie o arquivo de exemplo e ajuste:

```powershell
Copy-Item CONFIG_EXAMPLE.yaml aulaforge.yaml
```

> `aulaforge.yaml` é um arquivo **local de teste** e está no `.gitignore`. Não será commitado.

### Campos mais importantes

```yaml
project:
  output_dir: "./output"   # onde os arquivos gerados ficam
  language: "pt-BR"        # idioma das aulas para o Whisper

transcription:
  model: "base"            # modelos: tiny, base, small, medium, large
                           # "base" = mais rápido; "medium" = melhor qualidade

ocr:
  enabled: false           # OCR desativado por padrão; ative com true se quiser

notion:
  enabled: false           # Notion desativado por padrão; configure antes de ativar
  database_name: "Aulas Processadas"
  token_env_var: "NOTION_TOKEN"  # nome da variável de ambiente com o token

processing:
  retry_attempts: 3        # tentativas por step antes de marcar como FAILED
```

### Notion (opcional)

Para sincronizar com o Notion, defina o token como variável de ambiente:

```powershell
$env:NOTION_TOKEN = "secret_xxxx..."
```

E habilite no `aulaforge.yaml`:

```yaml
notion:
  enabled: true
  auto_send: true
```

---

## Como usar

### Comando principal

```powershell
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml
```

O AulaForge descobre todos os vídeos dentro da pasta, ordena por número de aula detectado no nome do arquivo, e processa cada aula em sequência.

### Flags disponíveis

| Flag | Descrição |
|---|---|
| `--config <arquivo>` | Caminho para o arquivo YAML de configuração. Se omitido, procura `./aulaforge.yaml`; se não existir, usa os defaults internos. |
| `--force` | Reprocessa todas as etapas mesmo que o vídeo e as entradas não tenham mudado. |
| `--resume` | Reprocessa apenas aulas cujo **último status** de algum step seja FAILED. Entradas antigas de falhas seguidas de sucesso não ativam o `--resume`. |

`--force` tem precedência sobre `--resume`.

### Exit codes

| Código | Significado |
|---|---|
| `0` | Tudo processado com sucesso |
| `1` | Pelo menos um step falhou por erro de processamento |
| `2` | Nenhuma falha de processamento, mas uma dependência local estava ausente (FFmpeg, Whisper, Ollama) |

### Exemplos

```powershell
# Primeira execução (processa tudo)
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml

# Segunda execução (pula o que não mudou)
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml

# Reprocessar apenas aulas com falhas recentes
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml --resume

# Forçar reprocessamento completo
aulaforge process-course "C:\Aulas\MeuCurso" --config aulaforge.yaml --force
```

---

## Outputs gerados

Os arquivos são gerados dentro de `output/<NomeDoCurso>/`.

### Por aula (`output/NomeDoCurso/<slug-da-aula>/`)

| Arquivo | Fase | Descrição |
|---|---|---|
| `source_info.json` | 1 | Fingerprint do vídeo (hash, tamanho, data) |
| `processing_log.json` | 1 | Histórico de steps com status e timestamps |
| `01_TRANSCRICAO_BRUTA.txt` | 2 | Transcrição bruta do Whisper |
| `02_TRANSCRICAO_COM_TIMESTAMPS.json` | 2 | Segmentos com `start`, `end`, `text` |
| `03_TRANSCRICAO_LIMPA.md` | 2 | Blocos de ~15 min sem sobreposição |
| `04_OCR_TELA.json` | 5 | Resultado OCR por frame (somente se `ocr.enabled: true`) |
| `05_OCR_TELA.md` | 5 | Resumo OCR legível (somente se `ocr.enabled: true`) |
| `06_CODIGOS_DETECTADOS.md` | 5 | Blocos de código extraídos (somente se `ocr.enabled: true`) |
| `07_COMANDOS_TERMINAL.md` | 5 | Comandos de terminal extraídos (somente se `ocr.enabled: true`) |
| `08_MERGE_AUDIO_VIDEO.md` | 6 | Linha do tempo integrada: transcrição + OCR |
| `09_ANOTACAO_NOTION.md` | 3 | Notas estruturadas geradas pelo Ollama |
| `10_CLAUDE_CODE_CONTEXT.md` | 7 | Contexto para uso no Claude Code |
| `11_CODEX_CONTEXT.md` | 7 | Contexto para uso no Codex |
| `12_PROMPTS_PRONTOS.md` | 7 | Prompts gerados automaticamente |
| `13_AGENTES_SUGERIDOS.md` | 7 | Sugestões de agentes derivados da aula |
| `14_SKILLS_SUGERIDAS.md` | 7 | Sugestões de skills derivadas da aula |
| `15_IDEIAS_DE_PROJETOS.md` | 7 | Ideias de projetos baseadas na aula |
| `16_IMPLEMENTATION_PLAN.md` | 7 | Plano de implementação gerado |

### Por curso (`output/NomeDoCurso/`)

| Arquivo | Descrição |
|---|---|
| `batch_report.md` | Tabela com status e timing de cada aula por step |
| `batch_log.json` | Log estruturado em JSON do batch |
| `COURSE_OVERVIEW.md` | Resumo executivo consolidado do curso |
| `COURSE_PROJECT_IDEAS.md` | Ideias de projetos agregadas de todas as aulas |
| `COURSE_AGENTS.md` | Agentes sugeridos agregados de todas as aulas |
| `COURSE_SKILLS.md` | Skills sugeridas agregadas de todas as aulas |
| `COURSE_PROMPTS.md` | Prompts prontos agregados de todas as aulas |

---

## Modos de operação

### Completo (transcrição + notas + Notion + OCR)

```yaml
ocr:
  enabled: true
notion:
  enabled: true
  auto_send: true
```

Requer: FFmpeg, Whisper, Ollama, Tesseract, token do Notion.

### Sem Notion (padrão recomendado para começar)

```yaml
notion:
  enabled: false
```

Requer: FFmpeg, Whisper, Ollama.

### Sem OCR (padrão)

```yaml
ocr:
  enabled: false
```

OCR é opt-in pois pode ser lento em vídeos longos.

### Mínimo (só transcrição, sem notas)

Se o Ollama não estiver disponível, o AulaForge processa normalmente até onde consegue. O step de notas é marcado como `FAILED` por dependência de Ollama. Os steps de merge e outputs continuam normalmente se a transcrição tiver sido concluída. O sistema não aborta — continua processando as demais aulas e retorna exit code `2`.

---

## Nomeação de aulas

O AulaForge detecta o número da aula pelo nome do arquivo:

| Nome do arquivo | Número detectado | Slug gerado |
|---|---|---|
| `Aula 01 - Introducao.mp4` | 1 | `aula_01_introducao` |
| `01 - Introducao.mp4` | 1 | `aula_01_introducao` |
| `Modulo T01 - Aula 6 - Título.mkv` | 6 | `aula_06_titulo` |
| `introducao.mp4` | nenhum | `aula_introducao` |

Arquivos sem número detectado são ordenados alfabeticamente e processados por último. Um aviso é emitido no log.

---

## Idempotência e checkpoints

O AulaForge é idempotente: executar o mesmo comando duas vezes não reprocessa o que não mudou.

Cada aula mantém um `source_info.json` com o hash SHA-256 do vídeo. Se o vídeo não mudou e os arquivos de saída já existem, o step é marcado como `SKIPPED_UNCHANGED`.

O `batch_report.md` exibe o status e o tempo de cada step por aula após cada execução.

---

## Troubleshooting

### `FP16 is not supported on CPU; using FP32 instead`

Mensagem normal do Whisper quando rodando em CPU (sem GPU). Não afeta o resultado — apenas usa mais memória e é mais lento. Pode ser ignorada.

### `Unable to find a suitable output format`

Erro do FFmpeg ao extrair áudio. Corrigido na versão atual (`audio.tmp.mp3` em vez de `audio.mp3.tmp`). Este bug foi corrigido na Fase 9. Se o erro aparecer, certifique-se de estar na branch `master` atualizada.

### `--resume` reprocessa aulas que já passaram

Comportamento corrigido na versão atual. O `--resume` agora considera apenas o **último status** de cada step, não falhas antigas no histórico. Se uma aula falhou em uma execução anterior mas foi reprocessada com sucesso depois, o `--resume` a ignora corretamente.

### Transcrição muito lenta

Use um modelo menor:

```yaml
transcription:
  model: "base"   # ou "tiny" para máxima velocidade
```

### Ollama não encontrado

Verifique se o Ollama está rodando:

```powershell
ollama list
```

Se o serviço não estiver iniciado, inicie-o antes de rodar o AulaForge.

### Notion: `NOTION_TOKEN não encontrado`

O token deve ser definido como variável de ambiente, não no arquivo YAML:

```powershell
$env:NOTION_TOKEN = "secret_xxxx..."
```

### Aula com número não detectado

Se o nome do arquivo não contiver um padrão de número reconhecível (`Aula N`, `N - Título`, etc.), a aula é ordenada alfabeticamente com um aviso no log. Renomear o arquivo para incluir o número resolve o problema.

---

## Desenvolvimento

### Rodar os testes

```powershell
.venv\Scripts\python.exe -m pytest -q
```

### Verificar estilo de código

```powershell
.venv\Scripts\python.exe -m ruff check .
```

### Verificar tipos

```powershell
.venv\Scripts\python.exe -m mypy src
```

### Estrutura do projeto

```
src/aulaforge/
  cli.py            — Orquestrador e CLI (Typer)
  config.py         — Carregamento de configuração (YAML + Pydantic)
  discovery.py      — Descoberta e ordenação de vídeos
  models.py         — Modelos de dados (Pydantic)
  checkpoints.py    — Controle de checkpoints e processing_log.json
  reports.py        — Geração de batch_report.md e batch_log.json
  audio.py          — Extração de áudio via FFmpeg
  transcription.py  — Transcrição via Whisper local
  chunking.py       — Divisão da transcrição em blocos
  notes.py          — Geração de notas via Ollama
  ollama_client.py  — Cliente Ollama
  notion.py         — Sincronização com Notion
  notion_client.py  — Cliente REST do Notion
  video_frames.py   — Extração de frames de vídeo
  ocr.py            — OCR local via Tesseract
  merge.py          — Merge de transcrição + OCR por timestamp
  outputs.py        — Geração de outputs Claude Code / Codex
  logging_setup.py  — Configuração de logging
```

---

## Restrições de design

- Local-first: nenhuma API paga é usada.
- Processamento sequencial por padrão (estável para runs longas).
- Batch sem confirmações manuais (projetado para rodar à noite).
- Transcrição bruta e screenshots salvos localmente; não enviados ao Notion.
- `aulaforge.yaml` é arquivo local e não deve ser commitado (`.gitignore` já configurado).
