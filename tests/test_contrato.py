"""Contrato com a calculadora.

No ambiente interno: salve uma resposta REAL da calculadora em
tests/fixtures/resposta_calculadora.json e rode `pytest tests/test_contrato.py`.
O teste test_resposta_real valida que o leitor extrai os valores.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from auditoria_rt.calc import contrato
from auditoria_rt.calc.base import ParametroCalculo

P = [ParametroCalculo(dt.date(2026, 3, 1), "SP", "3550308", "27101921", "000", "000001", base=1_000_000, ref="a"),
     ParametroCalculo(dt.date(2026, 3, 1), "SP", "3550308", "27101259", "200", "200001", base=1_000_000, ref="b")]


def test_monta_requisicao():
    r = contrato.montar_requisicao(P, {})
    assert r["uf"] == "SP" and r["municipio"] == 3550308
    assert [i["cClassTrib"] for i in r["itens"]] == ["000001", "200001"]


def test_le_resposta_formato_nfe():
    resp = {"objetos": [
        {"nObj": 1, "tribCalc": {"IBSCBS": {"CST": "000", "gIBSCBS": {
            "vBC": 1000000, "gIBSUF": {"pIBSUF": 0.1, "vIBSUF": 1000.0},
            "gIBSMun": {"pIBSMun": 0.0, "vIBSMun": 0.0}, "gCBS": {"pCBS": 0.9, "vCBS": 9000.0}}}}},
        {"nObj": 2, "erro": "cClassTrib não aplicável"},
    ]}
    r = contrato.ler_resposta(resp, P)
    assert r[0].status == "OK" and r[0].v_cbs == 9000.0 and r[0].v_ibs_uf == 1000.0 and r[0].ref == "a"
    assert r[1].status == "ERRO" and "não aplicável" in r[1].mensagem


def test_resposta_real():
    arq = Path(__file__).parent / "fixtures" / "resposta_calculadora.json"
    if not arq.exists():
        pytest.skip("Salve uma resposta real em tests/fixtures/resposta_calculadora.json")
    resp = json.loads(arq.read_text(encoding="utf-8"))
    r = contrato.ler_resposta(resp, P[:1])
    assert r[0].status == "OK", r[0].mensagem
    assert r[0].v_cbs is not None
