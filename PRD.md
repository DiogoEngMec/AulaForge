# PRD — AulaForge

## 1. Nome do produto

**AulaForge**

## 2. Visão geral

O AulaForge é uma ferramenta local para transformar vídeos de aulas em uma base de conhecimento estruturada, útil para estudo, documentação técnica, planejamento de projetos, Claude Code, Codex e Notion.

O usuário fornece uma pasta de curso contendo vídeos nomeados em sequência, como:

```text
Curso Django CRM/
  aula 1 - introducao.mp4
  aula 2 - models e banco.mp4
  aula 3 - kanban.mp4
```

O AulaForge processa cada vídeo automaticamente, salva todos os artefatos localmente e cria/atualiza uma página do curso no Notion.

## 3. Objetivo principal

Permitir que o usuário execute um único comando local e receba, para cada aula:

- transcrição bruta;
- transcrição com timestamps;
- transcrição limpa;
- frames/screenshot locais;
- OCR do conteúdo visual;
- códigos e comandos detectados;
- anotação estruturada;
- arquivos `.md` para Claude Code e Codex;
- sugestões de agentes, skills, prompts e projetos;
- atualização automática no Notion.

## 4. Usuário principal

Usuário técnico que estuda por vídeos, usa Claude Code, Codex, Notion, programação, IA, marketing, tráfego pago, negócios e outros temas.

## 5. Premissas

- O sistema roda localmente no Windows.
- Não deve depender de APIs pagas.
- O modelo de linguagem principal será local via Ollama.
- O modelo inicial será `qwen3:30b`.
- A transcrição usará Whisper local.
- O Notion será atualizado via MCP.
- O processamento em lote deve ser automático e não pedir confirmação manual.
- O fluxo deve ser sequencial para maior estabilidade.

## 6. Requisitos funcionais

### RF01 — Processar curso por pasta

O usuário deve poder rodar:

```powershell
aulaforge process-course "C:\Aulas\Curso Django CRM"
```

O sistema deve detectar os vídeos da pasta e ordenar pelas numerações no nome.

### RF02 — Pular aulas já processadas

Se o vídeo não mudou desde o último processamento, o sistema deve pular a aula.

Comparar por:

- caminho;
- tamanho;
- data de modificação;
- hash do arquivo.

### RF03 — Extrair áudio

Para cada vídeo, extrair áudio com FFmpeg e salvar localmente.

### RF04 — Transcrever áudio

Usar Whisper local para gerar:

- transcrição bruta;
- timestamps;
- arquivo `.json` estruturado;
- arquivo `.txt` simples.

### RF05 — Dividir aula em blocos de 15 minutos

Cada aula deve ser segmentada em blocos de 15 minutos para facilitar processamento local com Ollama.

### RF06 — Gerar anotação estruturada

Gerar anotação em português, mantendo termos técnicos em inglês.

Modo padrão: documentação/projeto.

### RF07 — OCR do vídeo

Extrair frames e aplicar OCR local.

Detectar quando possível:

- código;
- terminal;
- VS Code/editor;
- navegador;
- slides;
- GitHub;
- documentação;
- Notion.

### RF08 — Merge entre fala e tela

Combinar transcrição + OCR por proximidade de timestamps.

Exemplo:

- fala em `00:12:10` explica `Pipeline`;
- tela em `00:12:15` mostra código `class Pipeline`;
- anotação final une os dois.

### RF09 — Notion

Criar ou atualizar uma página do curso no Notion.

Se a página já existir pelo nome do curso, atualizar.
Se não existir, criar.

Cada aula deve ficar em um bloco recolhível estilo Toggle Heading 1.

### RF10 — Salvar arquivos locais

Para cada aula, salvar todos os artefatos em uma pasta própria.

### RF11 — Gerar visão geral do curso

Depois de processar todas as aulas, gerar uma visão geral do curso.

### RF12 — Gerar arquivos para Claude Code e Codex

Gerar arquivos `.md` úteis para continuar o trabalho em agentes de programação.

### RF13 — Geração de ideias

Gerar ideias de:

- projetos;
- agentes;
- skills;
- prompts;
- planos de implementação.

## 7. Requisitos não funcionais

### RNF01 — Local-first

Processamento deve ser local sempre que possível.

### RNF02 — Sem custo de API

Não usar OpenAI, Anthropic ou serviços pagos por padrão.

### RNF03 — Resiliência

O processamento em lote não pode travar em uma aula com erro.

Deve registrar erro e continuar a próxima aula.

### RNF04 — Checkpoints

Cada etapa deve salvar checkpoints para permitir retomada.

### RNF05 — Logs

Gerar logs legíveis e arquivos de relatório.

### RNF06 — Reprodutibilidade

O mesmo vídeo com a mesma config deve gerar resultados consistentes.

### RNF07 — Clareza

Arquivos finais devem ser fáceis de abrir e entender manualmente.

## 8. Fora do escopo inicial

Não incluir no MVP inicial:

- interface web;
- autenticação de usuários;
- SaaS;
- upload remoto;
- processamento paralelo;
- edição de vídeo;
- screenshots dentro do Notion;
- geração automática de pastas `.claude/agents/` no projeto do usuário.

## 9. MVP 1

Primeira versão deve fazer:

1. ler pasta de curso;
2. ordenar vídeos;
3. extrair áudio;
4. transcrever com Whisper local;
5. dividir em blocos de 15 minutos;
6. gerar anotação local em Markdown via Ollama;
7. salvar arquivos locais;
8. gerar relatório final.

Notion pode entrar no MVP 1.5 se a integração MCP ainda não estiver pronta.

## 10. MVP 2

Adicionar:

- Notion MCP;
- criação/atualização de página do curso;
- toggle por aula;
- visão geral do curso.

## 11. MVP 3

Adicionar:

- OCR;
- frames;
- detecção de código;
- detecção de terminal;
- merge áudio + vídeo.

## 12. MVP 4

Adicionar:

- arquivos para Claude Code;
- arquivos para Codex;
- prompts prontos;
- ideias de agentes;
- ideias de skills;
- planos de implementação.
