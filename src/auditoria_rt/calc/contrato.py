"""Contrato com a calculadora da RFB  >>> PONTO DE AJUSTE NO AMBIENTE INTERNO <<<

Este é o ÚNICO arquivo que conhece o formato de requisição/resposta da
calculadora. Se a versão liberada usar outros nomes de campos, ajuste
`montar_requisicao` e, se necessário, `ler_resposta`.

O formato abaixo segue o modelo de entrada da calculadora de regime geral
(dados da operação + lista de itens com NCM, CST, cClassTrib, base de cálculo,
quantidade e unidade). A leitura da resposta é tolerante: procura recursivamente
os campos com os nomes do leiaute da NF-e (pIBSUF, vIBSUF, pCBS, vCBS, ...), que
é como a calculadora devolve o grupo de tributos calculados.

Use `auditoria-rt testar-conexoes` e o teste tests/test_contrato.py com uma
resposta real (salva em tests/fixtures/) para validar o ajuste.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from auditoria_rt.calc.base import ParametroCalculo, ResultadoCalculo


def montar_requisicao(grupo: list[ParametroCalculo], cfg: dict) -> dict:
    p0 = grupo[0]
    return {
        "id": str(uuid.uuid4()),
        "versao": cfg.get("versao_payload", "1.0.0"),
        "dataHoraEmissao": f"{p0.data.isoformat()}T12:00:00-03:00",
        "municipio": int(p0.c_mun) if str(p0.c_mun).isdigit() else None,
        "uf": p0.uf or None,
        "itens": [
            {
                "numero": n,
                "ncm": p.ncm or None,
                "cst": p.cst,
                "cClassTrib": p.cclasstrib,
                "baseCalculo": round(p.base, 2),
                "quantidade": p.quantidade,
                "unidade": p.u_trib or "UN",
            }
            for n, p in enumerate(grupo, 1)
        ],
    }


# ---------------------------------------------------------------- resposta

def _buscar(obj: Any, chave: str) -> Any:
    """Primeiro valor encontrado para `chave` em qualquer profundidade."""
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = _buscar(v, chave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _buscar(v, chave)
            if r is not None:
                return r
    return None


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _itens_resposta(resp: Any) -> list:
    for chave in ("objetos", "itens", "items", "resultado", "det"):
        v = _buscar(resp, chave)
        if isinstance(v, list) and v:
            return v
    return [resp] if isinstance(resp, dict) else []


def _numero(item: dict, padrao: int) -> int:
    for chave in ("nObj", "numero", "nItem", "item"):
        v = item.get(chave) if isinstance(item, dict) else None
        if v is not None and str(v).isdigit():
            return int(v)
    return padrao


def _grupo(item: dict, nome: str) -> Any:
    g = _buscar(item, nome)
    return g if isinstance(g, dict) else item


def ler_resposta(resp: Any, grupo: list[ParametroCalculo]) -> list[ResultadoCalculo]:
    itens = _itens_resposta(resp)
    por_numero = {_numero(it, n): it for n, it in enumerate(itens, 1)}
    resultados = []
    for n, p in enumerate(grupo, 1):
        it = por_numero.get(n)
        if it is None:
            resultados.append(ResultadoCalculo(ref=p.ref, status="ERRO",
                                               mensagem="Item ausente na resposta da calculadora"))
            continue
        erro = _buscar(it, "erro") or _buscar(it, "mensagemErro")
        g_uf, g_mun, g_cbs = _grupo(it, "gIBSUF"), _grupo(it, "gIBSMun"), _grupo(it, "gCBS")
        r = ResultadoCalculo(
            ref=p.ref,
            status="ERRO" if erro else "OK",
            mensagem=str(erro) if erro else None,
            p_ibs_uf=_num(_buscar(g_uf, "pIBSUF")),
            p_ibs_mun=_num(_buscar(g_mun, "pIBSMun")),
            p_cbs=_num(_buscar(g_cbs, "pCBS")),
            v_ibs_uf=_num(_buscar(g_uf, "vIBSUF")),
            v_ibs_mun=_num(_buscar(g_mun, "vIBSMun")),
            v_cbs=_num(_buscar(g_cbs, "vCBS")),
            v_ibs_mono=_num(_buscar(it, "vIBSMono")),
            v_cbs_mono=_num(_buscar(it, "vCBSMono")),
            resposta=json.dumps(it, ensure_ascii=False)[:4000],
        )
        if r.status == "OK" and r.v_cbs is None and r.v_ibs_uf is None and r.v_ibs_mono is None:
            r.status, r.mensagem = "ERRO", "Resposta sem valores de IBS/CBS"
        resultados.append(r)
    return resultados


def ler_erro(status_http: int, corpo: str) -> str:
    try:
        j = json.loads(corpo)
        msg = _buscar(j, "mensagem") or _buscar(j, "message") or _buscar(j, "erro") or corpo
    except (ValueError, TypeError):
        msg = corpo
    return f"HTTP {status_http}: {str(msg)[:500]}"
