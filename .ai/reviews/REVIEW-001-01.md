---
schema: ai-review/v1
id: REVIEW-TASK-001-001
task_id: TASK-001
iteration: 1
actor:
  role: verifier
  agent: Joshua
  runtime: codex
  model: gpt-5.6
  config_commit: "d7dc2be653ce999f5616849cc5b8752875dbc2da"
created_at: 2026-08-10T13:06:14Z
reviewed_commit: "d7dc2be653ce999f5616849cc5b8752875dbc2da"
verdict: CHANGES_REQUIRED
findings:
  critical: 0
  high: 0
  medium: 1
  low: 0
supersedes: null
---

# Revisão técnica da TASK-001

A implementação fornece o banco PostgreSQL descartável, as fixtures compostas, o armazenamento temporário, o cliente FastAPI e o exercício bidirecional da cadeia Alembic. A suíte executou com 42 testes aprovados, e a indisponibilidade do PostgreSQL gerou uma mensagem operacional clara. Entretanto, o caminho de falha do primeiro upgrade pode deixar o banco descartável persistente, contrariando um requisito explícito da tarefa.

## Achados

### A — Falha no primeiro upgrade deixa o banco descartável sem limpeza

ID: REVIEW-001-01-A  
Severity: MEDIUM  
Confidence: HIGH  
Category: Resource leak / error handling  
Affected code: `tests/conftest.py:82-105`, `tests/conftest.py:108-111`  
Evidence: `pytest_configure` cria o banco em `tests/conftest.py:86`, mas somente grava `admin_url` e `test_db_name` em `_state` nas linhas 104-105, depois de `command.upgrade(..., "head")` na linha 102. Se qualquer revisão falhar nesse primeiro upgrade, a exceção ocorre antes do registro. Em seguida, `pytest_unconfigure` retorna imediatamente nas linhas 110-111 porque `test_db_name` não existe no estado.  
Impact: justamente uma quebra de migration que o harness deve detectar deixa um banco `grademate_test_*` persistente. Execuções repetidas acumulam bancos no PostgreSQL de desenvolvimento ou CI, e o requisito de que um teste com falha não deixe banco residual não é atendido.

## Evidência de verificação

- `.venv/bin/pytest -q -p no:cacheprovider`: 42 testes aprovados; 6 avisos de depreciação.
- PostgreSQL apontado para `127.0.0.1:1`: encerramento controlado com instrução para iniciar `docker compose up -d db`, sem traceback de conexão.
- A árvore Git permaneceu limpa após as verificações.

## Avaliação final

O caminho bem-sucedido e a maior parte dos critérios de aceitação estão cobertos, mas o vazamento determinístico no caminho de falha do upgrade viola o comportamento de limpeza exigido pela TASK-001. Por isso, a revisão não pode ser aprovada nesta iteração.

CHANGES_REQUIRED
