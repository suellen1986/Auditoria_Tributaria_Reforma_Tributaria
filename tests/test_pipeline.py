"""Teste de ponta a ponta: arquivos XML -> extração -> parse -> calculadora (tabela) -> regras -> relatório."""

import datetime as dt
import json

import openpyxl
import pytest

from auditoria_rt import pipeline
from auditoria_rt.sintetico import ItemSint, NotaSint, chave_sintetica, gerar_xml
from auditoria_rt.workspace import Workspace

DE, ATE = dt.date(2026, 3, 1), dt.date(2026, 3, 31)


def _cenarios() -> dict[str, NotaSint]:
    c = lambda n: chave_sintetica(n)  # noqa: E731
    return {
        "ok": NotaSint(c(1), itens=[ItemSint(c_prod="OK1"), ItemSint(v_prod=2500, ncm="38260000", c_prod="OK2")]),
        "cbs_errada": NotaSint(c(2), itens=[ItemSint(v_cbs=9.5)]),
        "cclass_invalido": NotaSint(c(3), itens=[ItemSint(cclasstrib="000999")]),
        "sem_ibscbs": NotaSint(c(4), itens=[ItemSint(sem_ibscbs=True)]),
        "total_errado": NotaSint(c(5), tot_override={"vCBS": 100.0}),
        "red_errada": NotaSint(c(6), itens=[ItemSint(cst="200", cclasstrib="200001", p_red=60, p_aliq_efet_cbs=0.5)]),
        "red_falta_grupo": NotaSint(c(7), itens=[ItemSint(cst="200", cclasstrib="200001")]),
        "mono_errado": NotaSint(c(8), itens=[ItemSint(cst="620", cclasstrib="620001", ncm="27101259",
                                                      mono={"q": 1000, "ad_rem_ibs": 0.1, "ad_rem_cbs": 0.2, "v_cbs": 250})]),
        "aliq_errada": NotaSint(c(9), itens=[ItemSint(p_cbs=1.0)]),
        "sem_tot": NotaSint(c(10), sem_tot=True),
        "diferimento_ok": NotaSint(c(11), itens=[ItemSint(cst="510", cclasstrib="510001", p_dif=100)]),
        "matriz": NotaSint(c(12), itens=[ItemSint(ncm="27101259")]),
    }


@pytest.fixture
def executado(cfg_teste):
    xml_dir = cfg_teste["extracao"]["fontes"][0]["diretorio"]
    cen = _cenarios()
    from pathlib import Path
    for nome, nota in cen.items():
        (Path(xml_dir) / f"{nome}.xml").write_text(gerar_xml(nota), encoding="utf-8")
    (Path(xml_dir) / "quebrado.xml").write_text("<nfeProc><NFe><infNFe><dhEmi>2026-03-10T00:00:00", encoding="utf-8")
    # duplicata: mesma nota em outro arquivo
    (Path(xml_dir) / "ok_duplicada.xml").write_text(gerar_xml(cen["ok"]), encoding="utf-8")
    ws = Workspace(cfg_teste)
    resumo = pipeline.executar_tudo(ws, DE, ATE, extrair_sap=True, workers=1)
    yield ws, resumo, cen
    ws.fechar()


def _regras_por_chave(ws, execucao):
    out = {}
    for regra, chave in ws.con.execute("SELECT regra, chave FROM desvios WHERE execucao = ?", [execucao]).fetchall():
        out.setdefault(chave, set()).add(regra)
    return out


def test_pipeline_completo(executado):
    ws, resumo, cen = executado
    ex = resumo["execucao"]
    assert resumo["processamento"]["notas"] == len(cen) + 1  # + duplicata
    assert resumo["processamento"]["erros"] == 1
    assert all(r["status"] == "OK" for r in resumo["regras"]), resumo["regras"]
    hits = _regras_por_chave(ws, ex)
    k = {n: s.chave for n, s in cen.items()}

    # nota correta: só pode ter a duplicidade
    assert hits.get(k["ok"], set()) == {"R019"}
    assert {"R011", "C001"} <= hits[k["cbs_errada"]]
    assert "R003" in hits[k["cclass_invalido"]] and "C005" in hits[k["cclass_invalido"]]
    assert "R001" in hits[k["sem_ibscbs"]]
    assert "R013" in hits[k["total_errado"]]
    assert {"R007", "C004"} <= hits[k["red_errada"]]
    assert "R005" in hits[k["red_falta_grupo"]]
    assert "R015" in hits[k["mono_errado"]]
    assert {"R016", "C001", "C004"} <= hits[k["aliq_errada"]]
    assert "R018" in hits[k["sem_tot"]]
    assert not ({"R009", "R010", "R011", "C001", "C002", "C003"} & hits.get(k["diferimento_ok"], set()))
    assert "E001" in hits[k["matriz"]]
    assert any(r == {"R000"} for r in hits.values())
    # P002: o mesmo produto PRD001 aparece com classificações diferentes entre os cenários
    assert "P002" in hits[k["cbs_errada"]] or "P002" in hits[k["red_errada"]]


def test_amostra_confere_atalho(executado):
    ws, resumo, _ = executado
    n = ws.con.execute("SELECT count(*) FROM calc_amostra WHERE execucao = ?", [resumo["execucao"]]).fetchall()[0][0]
    assert n > 0
    c007 = ws.con.execute("SELECT count(*) FROM desvios WHERE execucao = ? AND regra = 'C007'",
                          [resumo["execucao"]]).fetchall()[0][0]
    assert c007 == 0


def test_relatorio(executado):
    ws, resumo, _ = executado
    wb = openpyxl.load_workbook(resumo["relatorio"], read_only=True)
    assert {"Leia-me", "Resumo por regra", "Detalhe (top)", "Catálogo de regras"} <= set(wb.sheetnames)
    pasta = ws.dir_saidas / resumo["execucao"]
    man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert man["contagens"]["desvios"] > 0
    assert man["alertas"]  # tabela de exemplo deve gerar alerta
    assert (pasta / "desvios_detalhe.parquet").exists()


def test_reexecucao_idempotente(executado, cfg_teste):
    ws, resumo, _ = executado
    cache = ws.con.execute("SELECT count(*) FROM calc_aliquotas").fetchall()[0][0]
    r2 = pipeline.executar_tudo(ws, DE, ATE, extrair_sap=True, workers=1)
    assert r2["extracao"]["puladas"] > 0 and r2["processamento"]["processados"] == 0
    assert r2["calculo"]["aliquotas"]["pendentes"] == 0
    assert ws.con.execute("SELECT count(*) FROM calc_aliquotas").fetchall()[0][0] == cache
