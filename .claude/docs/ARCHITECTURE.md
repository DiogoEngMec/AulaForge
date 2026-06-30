# Arquitetura — AulaForge

## Visão geral

O AulaForge deve ser implementado como pipeline local modular.

```text
Curso local
  ↓
CourseScanner
  ↓
LessonPipeline
  ↓
AudioExtractor
  ↓
Transcriber
  ↓
Chunker
  ↓
OCRPipeline
  ↓
AudioVideoMerger
  ↓
NoteGenerator
  ↓
OutputWriter
  ↓
NotionPublisher
  ↓
BatchReporter
```

## Módulos principais

### 1. CLI

Responsável por receber comandos.

Comandos planejados:

```powershell
aulaforge process-course "C:\Aulas\Curso"
aulaforge process-course "C:\Aulas\Curso" --force
aulaforge inspect-course "C:\Aulas\Curso"
aulaforge doctor
aulaforge version
```

### 2. Config

Carrega `config.yaml` e valores padrão.

Responsável por:

- modelo Ollama;
- chunk de 15 minutos;
- diretório de saída;
- OCR on/off;
- Notion on/off;
- retry;
- skip unchanged.

### 3. CourseScanner

Responsável por:

- encontrar vídeos;
- ordenar por número da aula;
- extrair título amigável;
- criar objetos `Course` e `Lesson`.

### 4. CheckpointManager

Responsável por:

- hash;
- source_info;
- status da aula;
- pular aula igual;
- retomar etapas concluídas.

### 5. AudioExtractor

Usa FFmpeg para extrair áudio.

Entrada: vídeo.
Saída: áudio local.

### 6. Transcriber

Usa Whisper local.

Saídas:

- texto bruto;
- segmentos com timestamps;
- json estruturado.

### 7. Chunker

Divide a transcrição em blocos de 15 minutos.

### 8. OCRPipeline

Extrai frames e aplica OCR.

Responsável por:

- salvar screenshots localmente;
- deduplicar frames semelhantes;
- identificar possíveis códigos;
- identificar possíveis comandos;
- classificar confiança.

### 9. AudioVideoMerger

Une transcrição e OCR por timestamp.

### 10. LLM/Ollama

Cliente local para o Ollama.

Usado para:

- classificar tema;
- gerar resumo;
- organizar conteúdo;
- criar arquivos `.md` derivados.

### 11. OutputWriter

Salva todos os arquivos finais em Markdown, JSON e logs.

### 12. NotionPublisher

Publica no Notion via MCP.

Responsável por:

- criar página do curso;
- atualizar página existente;
- criar toggle por aula;
- atualizar visão geral.

### 13. BatchReporter

Gera `batch_report.md` e `batch_log.json`.

## Diretrizes arquiteturais

### Pipeline idempotente

Rodar duas vezes não deve duplicar output nem reprocessar aula sem necessidade.

### Local-first

Nunca exigir serviço externo além do Notion MCP configurado pelo usuário.

### Fail-soft

Erro em uma aula não deve parar o curso inteiro.

### Arquivos legíveis

Todo output deve poder ser lido manualmente.

### Separação de responsabilidades

Cada módulo deve fazer uma coisa bem definida.
