# Boas práticas de desenvolvimento — AulaForge

## Git

- Criar branch por fase.
- Commitar pequeno.
- Mensagem de commit objetiva.
- Testar antes do merge.

Exemplo:

```powershell
git switch -c phase-1-cli-foundation
git add .
git commit -m "Cria fundação CLI do AulaForge"
git push origin phase-1-cli-foundation
```

## Código

- Usar tipagem.
- Evitar funções gigantes.
- Separar módulos por responsabilidade.
- Não misturar lógica de Notion com lógica de pipeline.
- Não misturar lógica de CLI com lógica de domínio.

## Logs

- Logar início e fim de cada etapa.
- Logar tempo gasto por aula.
- Logar erros com contexto.

## Testes

- Testar parsers.
- Testar ordenação de aulas.
- Testar skip unchanged.
- Testar geração de paths.
- Testar chunking.

## UX do terminal

- Mensagens claras.
- Progresso visível.
- Relatório final.
- Nunca travar pedindo confirmação no batch.

## IA

- Prompts versionados.
- Salvar inputs e outputs importantes.
- Usar temperatura baixa.
- Dividir transcrições longas.
- Separar conteúdo original de insights.
