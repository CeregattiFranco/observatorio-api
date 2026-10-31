from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import duckdb

from .config import ACERVO_ROOT, DENY_SEGMENTS, PAINEL_ALLOWLIST
from .citation import detect_cc_by_nd, strip_internal_url


class Acervo:
    """Índice read-only do acervo público (metas + tabelas painel)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or ACERVO_ROOT).resolve()
        self._lock = threading.RLock()
        self._con = duckdb.connect(":memory:")
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._tabelas: dict[str, dict[str, Any]] = {}
        self._sha_index: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def ensure_loaded(self) -> None:
        with self._lock:
            if not self._loaded:
                self._load()
                self._loaded = True

    def _exec(self, sql: str, params=None):
        """DuckDB não é thread-safe: serializa todas as queries."""
        with self._lock:
            if not self._loaded:
                self._load()
                self._loaded = True
            if params is None:
                return self._con.execute(sql)
            return self._con.execute(sql, params)


    def reload(self) -> None:
        with self._lock:
            self._con.execute("DROP TABLE IF EXISTS metas")
            self._snapshots.clear()
            self._tabelas.clear()
            self._sha_index.clear()
            self._load()
            self._loaded = True

    def _denied(self, rel: str) -> bool:
        parts = set(Path(rel).parts)
        return bool(parts & DENY_SEGMENTS)

    def _load(self) -> None:
        if not self.root.is_dir():
            raise FileNotFoundError(f"ACERVO_ROOT inexistente: {self.root}")

        self._con.execute(
            """
            CREATE TABLE metas (
              id VARCHAR PRIMARY KEY,
              snapshot VARCHAR,
              item VARCHAR,
              papel VARCHAR,
              orgao VARCHAR,
              metodo VARCHAR,
              licenca VARCHAR,
              cc_by_nd BOOLEAN,
              arquivo VARCHAR,
              tamanho BIGINT,
              sha256 VARCHAR,
              url VARCHAR,
              baixado_em_utc VARCHAR,
              path_rel VARCHAR
            )
            """
        )

        foto = self.root / "fotografia"
        if not foto.is_dir():
            return

        rows: list[tuple] = []
        for snap_dir in sorted(p for p in foto.iterdir() if p.is_dir()):
            snap = snap_dir.name
            manifesto = snap_dir / "MANIFESTO.sha256"
            man_sha = None
            man_lines = 0
            if manifesto.is_file():
                raw = manifesto.read_bytes()
                man_sha = hashlib.sha256(raw).hexdigest()
                man_lines = raw.count(b"\n") + (0 if raw.endswith(b"\n") or not raw else 1)
                self._sha_index[man_sha] = {
                    "tipo": "manifesto",
                    "snapshot": snap,
                    "path": f"fotografia/{snap}/MANIFESTO.sha256",
                }
                # index each line hash -> path
                for line in raw.decode("utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(None, 1)
                    if len(parts) != 2:
                        continue
                    h, rel = parts[0], parts[1].lstrip("./")
                    full_rel = f"fotografia/{snap}/{rel}"
                    if self._denied(full_rel):
                        continue
                    self._sha_index[h] = {
                        "tipo": "manifesto_entry",
                        "snapshot": snap,
                        "path": full_rel,
                    }

            self._snapshots[snap] = {
                "id": snap,
                "manifest_linhas": man_lines,
                "manifest_sha256": man_sha,
                "path": f"fotografia/{snap}/",
            }

            for meta_path in snap_dir.rglob("*.meta.json"):
                rel = meta_path.relative_to(self.root).as_posix()
                if self._denied(rel):
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                arquivo = meta.get("arquivo") or meta_path.name.replace(".meta.json", "")
                sha = meta.get("sha256")
                mid = sha or hashlib.sha256(rel.encode()).hexdigest()
                lic = meta.get("licenca")
                url = strip_internal_url(meta.get("url") or meta.get("url_final"))
                rows.append(
                    (
                        mid,
                        snap,
                        meta.get("item"),
                        meta.get("papel"),
                        meta.get("orgao"),
                        meta.get("metodo"),
                        lic,
                        detect_cc_by_nd(lic),
                        arquivo,
                        meta.get("tamanho"),
                        sha,
                        url,
                        meta.get("baixado_em_utc"),
                        rel,
                    )
                )
                if sha:
                    self._sha_index[sha] = {
                        "tipo": "meta",
                        "snapshot": snap,
                        "path": rel,
                        "id": mid,
                    }

            # painel tables
            painel_dir = (
                snap_dir
                / "fonte-propria-nao-oficial"
                / "observatorio-tabelas-proprias"
            )
            if painel_dir.is_dir():
                for csv_gz in sorted(painel_dir.glob("painel.*.csv.gz")):
                    tid = csv_gz.name.replace(".csv.gz", "")
                    if tid not in PAINEL_ALLOWLIST:
                        continue
                    meta_p = Path(str(csv_gz) + ".meta.json")
                    meta = {}
                    if meta_p.is_file():
                        try:
                            meta = json.loads(meta_p.read_text(encoding="utf-8"))
                        except Exception:
                            meta = {}
                    rel = csv_gz.relative_to(self.root).as_posix()
                    sha = meta.get("sha256")
                    if not sha:
                        sha = hashlib.sha256(csv_gz.read_bytes()).hexdigest()
                    self._tabelas[tid] = {
                        "id": tid,
                        "snapshot": snap,
                        "path": rel,
                        "bytes_gz": csv_gz.stat().st_size,
                        "sha256": sha,
                        "licenca": meta.get("licenca") or "conteúdo próprio",
                        "orgao": meta.get("orgao") or "Co-labore / observatório da Ana",
                        "absolute": str(csv_gz),
                        "filters": sorted(PAINEL_ALLOWLIST[tid]["filters"]),
                    }
                    self._sha_index[sha] = {
                        "tipo": "tabela",
                        "snapshot": snap,
                        "path": rel,
                        "id": tid,
                    }

        if rows:
            self._con.executemany(
                "INSERT OR REPLACE INTO metas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

    # ---- queries ----

    def list_snapshots(self) -> list[dict[str, Any]]:
        self.ensure_loaded()
        return [self._snapshots[k] for k in sorted(self._snapshots)]

    def latest_snapshot_with_tabelas(self) -> str | None:
        self.ensure_loaded()
        snaps = sorted({t["snapshot"] for t in self._tabelas.values()}, reverse=True)
        return snaps[0] if snaps else (sorted(self._snapshots, reverse=True)[0] if self._snapshots else None)

    def list_tabelas(self) -> list[dict[str, Any]]:
        self.ensure_loaded()
        out = []
        for tid in sorted(self._tabelas):
            t = dict(self._tabelas[tid])
            t.pop("absolute", None)
            out.append(t)
        return out

    def get_tabela(self, tid: str) -> dict[str, Any] | None:
        self.ensure_loaded()
        t = self._tabelas.get(tid)
        if not t:
            return None
        # schema via duckdb describe
        abs_path = t["absolute"]
        desc = self._exec(
            "DESCRIBE SELECT * FROM read_csv_auto(?, header=true, sample_size=2048)",
            [abs_path],
        ).fetchall()
        # count (may be slow on large — ok for v0)
        n = self._exec(
            "SELECT COUNT(*) FROM read_csv_auto(?, header=true)",
            [abs_path],
        ).fetchone()[0]
        cols = [{"name": r[0], "type": r[1]} for r in desc]
        out = {k: v for k, v in t.items() if k != "absolute"}
        out["colunas"] = cols
        out["linhas"] = int(n)
        return out

    def query_linhas(
        self,
        tid: str,
        filters: dict[str, str],
        limit: int,
        offset: int,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        self.ensure_loaded()
        t = self._tabelas.get(tid)
        if not t:
            raise KeyError(tid)
        allowed = PAINEL_ALLOWLIST[tid]["filters"]
        where = []
        params: list[Any] = [t["absolute"]]
        for k, v in filters.items():
            if k not in allowed:
                raise ValueError(f"filtro não permitido: {k}")
            # cast-safe equality as varchar
            where.append(f"CAST({k} AS VARCHAR) = ?")
            params.append(v)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        count_sql = f"SELECT COUNT(*) FROM read_csv_auto(?, header=true){where_sql}"
        total = self._exec(count_sql, params).fetchone()[0]
        # column names
        desc = self._exec(
            "DESCRIBE SELECT * FROM read_csv_auto(?, header=true, sample_size=512)",
            [t["absolute"]],
        ).fetchall()
        colnames = [r[0] for r in desc]
        qparams = list(params) + [limit, offset]
        sql = (
            f"SELECT * FROM read_csv_auto(?, header=true){where_sql} "
            f"LIMIT ? OFFSET ?"
        )
        rows = self._exec(sql, qparams).fetchall()
        data = [dict(zip(colnames, row)) for row in rows]
        return colnames, data, int(total)

    def list_metas(
        self,
        *,
        snapshot: str | None = None,
        orgao: str | None = None,
        item: str | None = None,
        cc_by_nd: bool | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        self.ensure_loaded()
        clauses = []
        params: list[Any] = []
        if snapshot:
            clauses.append("snapshot = ?")
            params.append(snapshot)
        if orgao:
            clauses.append("lower(orgao) LIKE ?")
            params.append(f"%{orgao.casefold()}%")
        if item:
            clauses.append("lower(item) LIKE ?")
            params.append(f"%{item.casefold()}%")
        if cc_by_nd is not None:
            clauses.append("cc_by_nd = ?")
            params.append(cc_by_nd)
        if q:
            clauses.append(
                "(lower(coalesce(item,'')) LIKE ? OR lower(coalesce(papel,'')) LIKE ? "
                "OR lower(coalesce(orgao,'')) LIKE ? OR lower(coalesce(arquivo,'')) LIKE ?)"
            )
            qq = f"%{q.casefold()}%"
            params.extend([qq, qq, qq, qq])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        total = self._exec(f"SELECT COUNT(*) FROM metas{where}", params).fetchone()[0]
        sql = f"SELECT * FROM metas{where} ORDER BY snapshot DESC, item NULLS LAST LIMIT ? OFFSET ?"
        params2 = list(params) + [limit, offset]
        cur = self._exec(sql, params2)
        cols = [d[0] for d in cur.description]
        records = [dict(zip(cols, row)) for row in cur.fetchall()]
        return records, int(total)

    def get_meta(self, mid: str) -> dict[str, Any] | None:
        self.ensure_loaded()
        cur = self._exec("SELECT * FROM metas WHERE id = ?", [mid])
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip(cols, row))

    def verificar(self, sha256: str) -> dict[str, Any] | None:
        self.ensure_loaded()
        return self._sha_index.get(sha256.casefold()) or self._sha_index.get(sha256)

    def snapshot_manifest_sha(self, snapshot: str | None) -> str | None:
        self.ensure_loaded()
        if not snapshot:
            return None
        s = self._snapshots.get(snapshot)
        return s.get("manifest_sha256") if s else None


_acervo: Acervo | None = None


def get_acervo() -> Acervo:
    global _acervo
    if _acervo is None:
        _acervo = Acervo()
    return _acervo


def reset_acervo_for_tests(root: Path) -> Acervo:
    global _acervo
    _acervo = Acervo(root)
    _acervo.ensure_loaded()
    return _acervo
