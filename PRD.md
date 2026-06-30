# PRD — AulaForge

## 1. Visão geral

AulaForge é uma ferramenta local para processar cursos gravados em vídeo e transformar cada aula em documentação estruturada, notas no Notion e arquivos de contexto para Claude Code e Codex.

## 2. Problema

Aulas em vídeo são difíceis de consultar depois. A transcrição por áudio sozinha perde informações visuais importantes, como código exibido no VS Code, comandos no terminal, slides e páginas abertas no navegador.

## 3. Objetivo

Criar um pipeline local que:

1. leia uma pasta de curso;
2. ordene vídeos por número de aula;
3. extraia áudio;
4. transcreva com Whisper local;
5. extraia frames;
6. aplique OCR local;
7. detecte código e comandos;
8. faça merge entre fala e tela;
9. organize tudo com Ollama `qwen3:30b`;
10. gere Markdown local;
11. crie ou atualize uma página do curso no Notion via MCP;
12. gere arquivos para Claude Code e Codex.

## 4. Perfil de uso

O usuário deve poder rodar:

```powershell
python -m aulaforge process-course "C:\Aulas\Curso Django CRM"
```

E deixar o processamento rodando durante a madrugada sem intervenção manual.

## 5. Requisitos funcionais

- Detectar nome do curso pela pasta.
- Detectar ordem das aulas pelo número no nome do arquivo.
- Pular aula já processada se o vídeo não mudou.
- Processar uma aula por vez.
- Salvar logs e checkpoints.
- Continuar o lote em caso de erro em uma aula.
- Gerar relatório final do curso.
- Criar página no Notion se não existir.
- Atualizar página no Notion se já existir.
- Criar uma seção recolhível por aula.
- Gerar visão geral do curso após processar todas as aulas.

## 6. Requisitos não funcionais

- Local-first.
- Sem custos de API.
- Robusto para batch.
- Fácil de auditar.
- Arquitetura modular.
- Testável.
- Preparado para evoluir por fases.

## 7. Fora de escopo inicial

- Interface web.
- Processamento paralelo.
- Upload de vídeos para nuvem.
- Uso de APIs pagas.
- Edição automática de vídeo.
