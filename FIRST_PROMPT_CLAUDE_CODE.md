# Primeiro prompt para usar no Claude Code

Antes de colar este prompt no Claude Code, faça:

1. Crie a pasta do projeto `AulaForge`.
2. Extraia este pacote na raiz do projeto.
3. Confirme que existem estas pastas:
   - `.claude/agents/`
   - `.claude/skills/aulaforge/`
   - `.claude/commands/`
   - `.claude/rules/`
   - `.claude/hooks/`
   - `.claude/docs/`
   - `.claude/prompts/`
4. Não precisa configurar Notion MCP ainda.
5. Não precisa instalar Whisper, FFmpeg, Ollama ou OCR antes da primeira conversa. A primeira conversa é apenas leitura e planejamento.
6. Confirme depois, antes da Fase 2+, que `qwen3:30b` existe no Ollama e que Whisper/FFmpeg estão acessíveis.

---

## Prompt completo

Você está no repositório AulaForge.

Antes de escrever qualquer código, faça uma fase de leitura e planejamento. Não implemente nada ainda.

### 1. Estrutura Claude Code

Considere que este projeto usa a estrutura:

- `.claude/CLAUDE.md` como memória persistente do projeto;
- `.claude/settings.json` como configuração compartilhada;
- `.claude/settings.local.json` como configuração local não versionada;
- `.claude/agents/` como subagentes especializados;
- `.claude/skills/aulaforge/SKILL.md` como workflow reutilizável do projeto;
- `.claude/commands/` como slash commands customizados;
- `.claude/rules/` como regras por área;
- `.claude/hooks/` como scripts auxiliares de segurança;
- `.claude/docs/` como documentação técnica de referência;
- `.claude/prompts/` como prompts por fase;
- `.claude/templates/` como templates de saída;
- `.claude/checklists/` como checklists de qualidade.

### 2. Leitura obrigatória

Leia primeiro:

1. `.claude/docs/FILE_READING_ORDER.md`

Depois siga a ordem completa definida nesse arquivo.

Ao terminar, confirme em uma tabela:

- arquivo;
- status: lido / ausente / não aplicável;
- resumo de 1 linha;
- como o arquivo influencia a Fase 1.

Se algum arquivo não existir, informe claramente.

### 3. Skill e agentes

Use a skill:

- `.claude/skills/aulaforge/SKILL.md`

Considere desde o início estes agentes:

- `.claude/agents/aulaforge-product-architect.md`
- `.claude/agents/python-cli-engineer.md`
- `.claude/agents/transcription-whisper-engineer.md`
- `.claude/agents/ollama-prompt-engineer.md`
- `.claude/agents/ocr-video-engineer.md`
- `.claude/agents/notion-mcp-integrator.md`
- `.claude/agents/audio-video-merge-engineer.md`
- `.claude/agents/qa-automation-engineer.md`
- `.claude/agents/docs-knowledge-engineer.md`

Não use todos ao mesmo tempo. Para o planejamento inicial, use principalmente:

- `aulaforge-product-architect` para validar produto e escopo;
- `python-cli-engineer` para validar fundação técnica;
- `qa-automation-engineer` para antecipar riscos de qualidade;
- `docs-knowledge-engineer` para garantir coerência documental.

### 4. Regras gerais

Respeite as regras em:

- `.claude/rules/local-first.md`
- `.claude/rules/python.md`
- `.claude/rules/notion.md`
- `.claude/rules/docs.md`

Pontos fundamentais:

- O projeto é local-first.
- Use Whisper local para transcrição.
- Use Ollama local com `qwen3:30b` para organização.
- Use OCR local.
- Não use APIs pagas ou externas para processar vídeo, áudio, transcrição ou OCR.
- O processamento deve ser sequencial.
- O sistema deve rodar em batch sem pedir confirmação manual.
- O projeto deve ser construído por fases.

### 5. Não implementar ainda

Neste primeiro momento, não edite arquivos e não implemente código.

Primeiro entregue:

1. seu entendimento do AulaForge;
2. resumo da arquitetura proposta;
3. sequência de fases do projeto;
4. escopo exato da Fase 1;
5. o que fica fora da Fase 1;
6. agentes que você recomenda usar/revisar em cada fase;
7. lista de arquivos e pastas que pretende criar na Fase 1;
8. riscos técnicos;
9. dúvidas bloqueantes;
10. critérios de aceite da Fase 1.

Aguarde minha aprovação antes de implementar.
