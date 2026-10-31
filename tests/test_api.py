def test_healthz(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_v0_has_citacao(client):
    r = client.get("/api/v0")
    assert r.status_code == 200
    body = r.json()
    assert "citacao" in body
    assert body["citacao"]["id"].startswith("colabore-obs:")
    assert "snapshot" in body["citacao"]


def test_snapshots(client):
    r = client.get("/api/v0/snapshots")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_metas_cc_by_nd_and_strip_postgres(client):
    r = client.get("/api/v0/metas", params={"limit": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert "citacao" in body
    # find IBGE meta
    ibge = [m for m in body["metas"] if m.get("orgao") == "IBGE"]
    assert ibge
    assert ibge[0]["cc_by_nd"] is True
    # painel meta should not expose postgres url
    for m in body["metas"]:
        url = m.get("url") or ""
        assert "postgres://" not in url
        assert "consultorio-db" not in url


def test_tabelas_and_linhas(client):
    r = client.get("/api/v0/tabelas")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["tabelas"]]
    assert "painel.regiao_vacina" in ids

    r2 = client.get("/api/v0/tabelas/painel.regiao_vacina")
    assert r2.status_code == 200
    assert r2.json()["tabela"]["linhas"] == 3

    r3 = client.get(
        "/api/v0/tabelas/painel.regiao_vacina/linhas",
        params={"ibge": "3550308", "limit": 10},
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["total"] == 2
    assert len(body["linhas"]) == 2
    assert body["citacao"]["artefato_sha256"]


def test_linhas_filtro_negado(client):
    r = client.get(
        "/api/v0/tabelas/painel.regiao_vacina/linhas",
        params={"doenca": "x"},
    )
    assert r.status_code == 400


def test_linhas_csv(client):
    r = client.get(
        "/api/v0/tabelas/painel.regiao_vacina/linhas",
        params={"formato": "csv", "limit": 5},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "ibge" in r.text.splitlines()[0]
    assert r.headers.get("X-Citacao-Sha256")


def test_verificar(client):
    # get sha from tabelas
    t = client.get("/api/v0/tabelas").json()["tabelas"][0]
    sha = t["sha256"]
    r = client.get(f"/api/v0/verificar/{sha}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get("/api/v0/verificar/" + ("0" * 64))
    assert r2.status_code == 200
    assert r2.json()["ok"] is False


def test_tabela_fora_allowlist(client):
    r = client.get("/api/v0/tabelas/painel.secreta/linhas")
    assert r.status_code == 404
