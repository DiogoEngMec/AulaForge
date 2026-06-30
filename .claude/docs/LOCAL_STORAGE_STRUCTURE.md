# Estrutura local de armazenamento — AulaForge

## Entrada

```text
C:\Aulas\Curso Django CRM\
  aula 1 - introducao.mp4
  aula 2 - models e banco.mp4
  aula 3 - kanban.mp4
```

## Saída

```text
output/
  Curso Django CRM/
    COURSE_OVERVIEW.md
    COURSE_PROJECT_IDEAS.md
    COURSE_AGENTS.md
    COURSE_SKILLS.md
    COURSE_PROMPTS.md
    COURSE_NOTION_PAGE.md
    course_state.json
    batch_report.md
    batch_log.json

    aula_01_introducao/
      source_info.json
      processing_log.json
      audio/
        audio.mp3
      frames/
        00-00-05.png
        00-00-10.png
      01_TRANSCRICAO_BRUTA.txt
      02_TRANSCRICAO_COM_TIMESTAMPS.json
      03_TRANSCRICAO_LIMPA.md
      03_CHUNKS_15_MIN.json
      04_OCR_TELA.json
      05_OCR_TELA.md
      06_CODIGOS_DETECTADOS.md
      07_COMANDOS_TERMINAL.md
      08_MERGE_AUDIO_VIDEO.md
      09_ANOTACAO_NOTION.md
      10_CLAUDE_CODE_CONTEXT.md
      11_CODEX_CONTEXT.md
      12_PROMPTS_PRONTOS.md
      13_AGENTES_SUGERIDOS.md
      14_SKILLS_SUGERIDAS.md
      15_IDEIAS_DE_PROJETOS.md
      16_IMPLEMENTATION_PLAN.md
```

## Regra

Nunca copiar o vídeo original para output por padrão.

Apenas referenciar o caminho original em `source_info.json`.
