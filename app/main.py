from __future__ import annotations

import csv
import io
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .acervo import get_acervo
from .citation import make_citacao
from .config import (
    API_ROOT_PATH,
    API_VERSION,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PAINEL_ALLOWLIST,
)

app = FastAPI(
    title="observatorio-api",
    version=API_VERSION,
    description="Consulta read-only do acervo público Co-labore (dados.co-labore.com/api).",
    root_path=API_ROOT_PATH or "",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def _envelope(payload: dict[str, Any], citacao: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["citacao"] = citacao
    return out


@app.on_event("startup")
def _startup() -> None:
    get_acervo().ensure_loaded()


@app.get("/healthz")
@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "versao": API_VERSION}


@app.get("/v0")
@app.get("/api/v0")
def v0_root() -> dict[str, Any]:
    ac = get_acervo()
    snap = ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        handle_suffix="root",
        licenca_texto="metadados e agregados públicos; ver cada artefato",
        orgao="Co-labore",
    )
    return _envelope(
        {
            "nome": "observatorio-api",
            "versao": API_VERSION,
            "principios": [
                "somente_leitura",
                "allowlist_acervo_publico",
                "separado_de_fachada_fhir",
                "citavel",
                "open_source_mit",
            ],
            "rotas": [
                "/api/healthz",
                "/api/v0",
                "/api/v0/snapshots",
                "/api/v0/fontes",
                "/api/v0/metas",
                "/api/v0/metas/{id}",
                "/api/v0/tabelas",
                "/api/v0/tabelas/{id}",
                "/api/v0/tabelas/{id}/linhas",
                "/api/v0/verificar/{sha256}",
            ],
            "openapi": "/openapi.json",
        },
        cit,
    )


@app.get("/v0/snapshots")
@app.get("/api/v0/snapshots")
def snapshots() -> dict[str, Any]:
    ac = get_acervo()
    items = ac.list_snapshots()
    snap = ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        handle_suffix="snapshots",
        orgao="Co-labore",
    )
    return _envelope({"snapshots": items, "total": len(items)}, cit)


@app.get("/v0/fontes")
@app.get("/api/v0/fontes")
def fontes(
    snapshot: Optional[str] = None,
    orgao: Optional[str] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Alias agregado: fontes distintas (orgao/item) a partir do catálogo de metas."""
    ac = get_acervo()
    lim = _clamp_limit(limit)
    rows, total = ac.list_metas(
        snapshot=snapshot, orgao=orgao, q=q, limit=lim, offset=max(0, offset)
    )
    # compact view for "fontes"
    fontes_out = [
        {
            "id": r["id"],
            "snapshot": r["snapshot"],
            "item": r["item"],
            "orgao": r["orgao"],
            "metodo": r["metodo"],
            "licenca": r["licenca"],
            "cc_by_nd": r["cc_by_nd"],
            "arquivo": r["arquivo"],
            "sha256": r["sha256"],
        }
        for r in rows
    ]
    snap = snapshot or ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        handle_suffix="fontes",
        orgao="Co-labore",
    )
    return _envelope(
        {"fontes": fontes_out, "total": total, "limit": lim, "offset": offset},
        cit,
    )


@app.get("/v0/metas")
@app.get("/api/v0/metas")
def metas(
    snapshot: Optional[str] = None,
    orgao: Optional[str] = None,
    item: Optional[str] = None,
    cc_by_nd: Optional[bool] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    ac = get_acervo()
    lim = _clamp_limit(limit)
    rows, total = ac.list_metas(
        snapshot=snapshot,
        orgao=orgao,
        item=item,
        cc_by_nd=cc_by_nd,
        q=q,
        limit=lim,
        offset=max(0, offset),
    )
    snap = snapshot or ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        handle_suffix="metas",
        orgao="Co-labore",
    )
    return _envelope(
        {"metas": rows, "total": total, "limit": lim, "offset": offset},
        cit,
    )


@app.get("/v0/metas/{mid}")
@app.get("/api/v0/metas/{mid}")
def meta_one(mid: str) -> dict[str, Any]:
    ac = get_acervo()
    row = ac.get_meta(mid)
    if not row:
        raise HTTPException(404, detail="meta não encontrada")
    cit = make_citacao(
        snapshot=row.get("snapshot"),
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(row.get("snapshot")),
        artefato=row.get("path_rel"),
        artefato_sha256=row.get("sha256"),
        licenca_texto=row.get("licenca"),
        orgao=row.get("orgao"),
        handle_suffix=mid[:16],
    )
    return _envelope({"meta": row}, cit)


@app.get("/v0/tabelas")
@app.get("/api/v0/tabelas")
def tabelas() -> dict[str, Any]:
    ac = get_acervo()
    items = ac.list_tabelas()
    snap = ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        handle_suffix="tabelas",
        licenca_texto="conteúdo próprio",
        orgao="Co-labore / observatório da Ana",
    )
    return _envelope({"tabelas": items, "total": len(items)}, cit)


@app.get("/v0/tabelas/{tid}")
@app.get("/api/v0/tabelas/{tid}")
def tabela_one(tid: str) -> dict[str, Any]:
    if tid not in PAINEL_ALLOWLIST:
        raise HTTPException(404, detail="tabela fora da allowlist")
    ac = get_acervo()
    try:
        t = ac.get_tabela(tid)
    except Exception as e:
        raise HTTPException(500, detail=f"falha ao ler tabela: {e}") from e
    if not t:
        raise HTTPException(404, detail="tabela não encontrada no acervo")
    cit = make_citacao(
        snapshot=t.get("snapshot"),
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(t.get("snapshot")),
        artefato=t.get("path"),
        artefato_sha256=t.get("sha256"),
        licenca_texto=t.get("licenca"),
        orgao=t.get("orgao"),
        handle_suffix=tid,
    )
    return _envelope({"tabela": t}, cit)


@app.get("/v0/tabelas/{tid}/linhas")
@app.get("/api/v0/tabelas/{tid}/linhas")
def tabela_linhas(
    request: Request,
    tid: str,
    limit: Optional[int] = None,
    offset: int = 0,
    formato: Optional[str] = Query(None, description="json|csv; também Accept"),
    ibge: Optional[str] = None,
    fonte: Optional[str] = None,
    uf: Optional[str] = None,
    ano: Optional[str] = None,
    mes: Optional[str] = None,
    vacina: Optional[str] = None,
    doenca: Optional[str] = None,
    regiao: Optional[str] = None,
    semana: Optional[str] = None,
    periodo: Optional[str] = None,
    codigo: Optional[str] = None,
    severidade: Optional[str] = None,
    indicador: Optional[str] = None,
) -> Response:
    if tid not in PAINEL_ALLOWLIST:
        raise HTTPException(404, detail="tabela fora da allowlist")
    ac = get_acervo()
    tmeta = ac.list_tabelas()
    tinfo = next((x for x in tmeta if x["id"] == tid), None)
    if not tinfo:
        raise HTTPException(404, detail="tabela não encontrada no acervo")

    raw_filters = {
        "ibge": ibge,
        "fonte": fonte,
        "uf": uf,
        "ano": ano,
        "mes": mes,
        "vacina": vacina,
        "doenca": doenca,
        "regiao": regiao,
        "semana": semana,
        "periodo": periodo,
        "codigo": codigo,
        "severidade": severidade,
        "indicador": indicador,
    }
    filters = {k: v for k, v in raw_filters.items() if v is not None}
    lim = _clamp_limit(limit)
    off = max(0, offset)
    try:
        colnames, data, total = ac.query_linhas(tid, filters, lim, off)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except KeyError:
        raise HTTPException(404, detail="tabela não encontrada") from None

    cit = make_citacao(
        snapshot=tinfo.get("snapshot"),
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(tinfo.get("snapshot")),
        artefato=tinfo.get("path"),
        artefato_sha256=tinfo.get("sha256"),
        licenca_texto=tinfo.get("licenca"),
        orgao=tinfo.get("orgao"),
        handle_suffix=tid,
    )

    want_csv = (formato or "").casefold() == "csv"
    accept = (request.headers.get("accept") or "").casefold()
    if not want_csv and "text/csv" in accept and "application/json" not in accept:
        want_csv = True

    if want_csv:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=colnames, extrasaction="ignore")
        w.writeheader()
        for row in data:
            w.writerow({k: row.get(k) for k in colnames})
        headers = {
            "X-Citacao-Id": cit["id"],
            "X-Citacao-Snapshot": str(cit.get("snapshot") or ""),
            "X-Citacao-Sha256": str(cit.get("artefato_sha256") or ""),
            "X-Total-Count": str(total),
            "Content-Disposition": f'attachment; filename="{tid}.csv"',
        }
        return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    return JSONResponse(
        _envelope(
            {
                "id": tid,
                "linhas": data,
                "colunas": colnames,
                "total": total,
                "limit": lim,
                "offset": off,
                "filtros": filters,
            },
            cit,
        )
    )


@app.get("/v0/verificar/{sha256}")
@app.get("/api/v0/verificar/{sha256}")
def verificar(sha256: str) -> dict[str, Any]:
    if len(sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha256):
        raise HTTPException(400, detail="sha256 deve ter 64 hex")
    ac = get_acervo()
    hit = ac.verificar(sha256)
    snap = (hit or {}).get("snapshot") or ac.latest_snapshot_with_tabelas()
    cit = make_citacao(
        snapshot=snap,
        snapshot_sha256_manifesto=ac.snapshot_manifest_sha(snap),
        artefato_sha256=sha256.casefold(),
        artefato=(hit or {}).get("path"),
        handle_suffix=f"verify:{sha256[:12]}",
        orgao="Co-labore",
    )
    if not hit:
        return _envelope({"ok": False, "sha256": sha256.casefold()}, cit)
    return _envelope({"ok": True, "sha256": sha256.casefold(), **hit}, cit)
