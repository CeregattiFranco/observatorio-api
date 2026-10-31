# observatorio-api

API **read-only** de consulta do acervo público Co-labore (`dados.co-labore.com/api`).

Stack: **FastAPI + DuckDB**. Licença **MIT**.

## Princípios

- Só lê `ACERVO_ROOT` (padrão: `~/acervo-publico`)
- Allowlist de tabelas `painel.*` — **sem SQL livre**
- Separado de `fachada-fhir` / prontuário
- Toda resposta JSON traz envelope `citacao` (snapshot, sha256, licença, flag CC BY-ND, handle)

## Rotas

| Método | Caminho |
|---|---|
| GET | `/api/healthz` |
| GET | `/api/v0` |
| GET | `/api/v0/snapshots` |
| GET | `/api/v0/fontes` |
| GET | `/api/v0/metas` |
| GET | `/api/v0/metas/{id}` |
| GET | `/api/v0/tabelas` |
| GET | `/api/v0/tabelas/{id}` |
| GET | `/api/v0/tabelas/{id}/linhas` |
| GET | `/api/v0/verificar/{sha256}` |

Prefixo `/api` também funciona sem prefixo no processo local (rotas duplicadas para smoke sem proxy).

## Desenvolvimento local (VPS)

```bash
cd ~/services/observatorio-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ACERVO_ROOT=$HOME/acervo-publico
export API_ROOT_PATH=/api
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
# curl http://127.0.0.1:8000/api/healthz
```

## Docker / Traefik

Ver `docker-compose.yml` (rascunho). **Não** fazer `docker pull` / `compose up` sem aprovação.

Imagem base proposta: `python:3.12-slim`.

## Decisões (t184s789)

- DuckDB + FastAPI
- URL: `dados.co-labore.com/api`
- Repo novo (scaffold local; GitHub sob aprovação)
- v0: painel + catálogo `.meta.json`

Design: `~/co-labore/pmbok/proposta-observatorio-api-v0.md`
