from __future__ import annotations

import os
from pathlib import Path

ACERVO_ROOT = Path(os.environ.get("ACERVO_ROOT", "/home/rodrigo/acervo-publico")).resolve()
API_ROOT_PATH = os.environ.get("API_ROOT_PATH", "/api").rstrip("/") or ""
API_VERSION = "0.1.0-dev"
HANDLE_PREFIX = "colabore-obs"
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
ESPELHO_URL = "https://dados.co-labore.com/"

# Tabelas allowlisted (só estas têm /linhas)
PAINEL_ALLOWLIST = {
    "painel.regiao_aviso": {
        "filters": {"codigo", "fonte", "severidade"},
        "columns": None,  # all
    },
    "painel.regiao_indicador": {
        "filters": {"ibge", "fonte"},
        "columns": None,
    },
    "painel.regiao_indicador_snapshot": {
        "filters": {"ibge", "fonte", "periodo"},
        "columns": None,
    },
    "painel.regiao_saude": {
        "filters": {"ibge", "fonte", "doenca", "uf", "regiao", "semana"},
        "columns": None,
    },
    "painel.regiao_vacina": {
        "filters": {"ibge", "ano", "mes", "vacina"},
        "columns": None,
    },
    "painel.sisvan_consumo": {
        "filters": {"uf", "indicador", "ano"},
        "columns": None,
    },
}

DENY_SEGMENTS = {
    "internacoes-sih",
    "saude-mental-sia",
    "saude-mental-sinan",
    "trabalho-nr-1-sinan",
    "trabalho-previdencia",
}
