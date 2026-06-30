# Schema da database Notion — AulaForge

## Database

Nome sugerido:

```text
Aulas Processadas
```

## Propriedades

### Título

Tipo: Title

Exemplo:

```text
Curso Django CRM
```

### Curso

Tipo: Text ou Select

Nome do curso detectado pela pasta.

### Categoria

Tipo: Select

Sugestões:

- Programação
- IA
- Claude Code
- Codex
- Marketing
- Tráfego Pago
- Notion
- Negócios
- Nutrição
- Outros

### Tema principal

Tipo: Text

Detectado automaticamente pelo Ollama.

### Subtemas

Tipo: Multi-select ou Text

Exemplos:

- Django
- CRM
- SaaS
- Tailwind
- Kanban

### Duração total

Tipo: Text ou Number

### Quantidade de aulas

Tipo: Number

### Data de processamento

Tipo: Date

### Status

Tipo: Select

Valores:

- Processado
- Processado com avisos
- Erro parcial
- Falhou

### Caminho local

Tipo: URL ou Text

Caminho da pasta local de saída.

### Tem OCR?

Tipo: Checkbox

### Tem código detectado?

Tipo: Checkbox

### Tem comandos detectados?

Tipo: Checkbox

### Modelo LLM

Tipo: Text

Exemplo:

```text
qwen3:30b
```

### Processado por

Tipo: Text

Exemplo:

```text
AulaForge
```
