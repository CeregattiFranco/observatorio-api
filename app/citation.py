from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import API_VERSION, ESPELHO_URL, HANDLE_PREFIX

BRT = ZoneInfo("America/Sao_Paulo")


def detect_cc_by_nd(licenca: str | None) -> bool:
    if not licenca:
        return False
    t = licenca.casefold()
    return "cc by-nd" in t or "cc-by-nd" in t or "by-nd" in t


def make_citacao(
    *,
    snapshot: str | None,
    artefato: str | None = None,
    artefato_sha256: str | None = None,
    snapshot_sha256_manifesto: str | None = None,
    licenca_texto: str | None = None,
    orgao: str | None = None,
    handle_suffix: str | None = None,
) -> dict[str, Any]:
    cc = detect_cc_by_nd(licenca_texto)
    suffix = handle_suffix or artefato or snapshot or "acervo"
    handle = f"{HANDLE_PREFIX}:{snapshot or 'n/a'}:{suffix}"
    now = datetime.now(BRT).isoformat(timespec="seconds")
    return {
        "id": handle,
        "snapshot": snapshot,
        "snapshot_sha256_manifesto": snapshot_sha256_manifesto,
        "artefato": artefato,
        "artefato_sha256": artefato_sha256,
        "licenca": {
            "texto": licenca_texto,
            "cc_by_nd": cc,
            "restritiva": cc,
        },
        "orgao": orgao,
        "espelho": ESPELHO_URL,
        "gerado_em": now,
        "api_versao": API_VERSION,
    }


def strip_internal_url(url: str | None) -> str | None:
    if not url:
        return url
    low = url.casefold()
    if low.startswith("postgres://") or low.startswith("postgresql://") or "consultorio-db" in low:
        return None
    return url
