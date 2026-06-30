# QA — AulaForge

## Objetivo

Garantir que o AulaForge funcione de forma confiável em lote, sem travar, e gere outputs úteis.

## Testes essenciais

### 1. Scanner de curso

- Detecta vídeos.
- Ignora arquivos não-vídeo.
- Ordena corretamente `aula 1`, `aula 2`, `aula 10`.

### 2. Slug e paths

- Gera nomes de pastas seguros.
- Não quebra com acentos.
- Não quebra com espaços.

### 3. Hash/checkpoint

- Detecta aula já processada.
- Reprocessa quando arquivo muda.
- Reprocessa com `--force`.

### 4. Áudio

- Verifica FFmpeg.
- Gera áudio válido.
- Registra erro se FFmpeg falhar.

### 5. Transcrição

- Gera `.txt`.
- Gera `.json`.
- Gera timestamps.
- Não para o lote inteiro se falhar.

### 6. Chunking

- Segmenta em blocos de 15 minutos.
- Mantém timestamps corretos.

### 7. Ollama

- Verifica se Ollama está rodando.
- Verifica se o modelo existe.
- Faz retry se falhar.
- Salva erro legível.

### 8. Notion

- Não duplica página do curso.
- Não duplica aula já publicada.
- Se falhar, salva local e continua.

### 9. OCR

- Salva frames.
- Salva OCR bruto.
- Classifica confiança.
- Não trava se OCR falhar.

## Critérios de pronto para cada fase

Uma fase só deve ser considerada pronta se:

- tem comando para testar;
- tem pelo menos validação manual clara;
- não quebra fluxo anterior;
- atualiza documentação se necessário;
- gera logs suficientes.
