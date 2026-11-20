"""Orquestra o uso da calculadora em escala.

Estratégia (milhões de itens):
  1. Atalho: extrai as combinações DISTINTAS de parâmetros que definem a alíquota
     (data/mês, UF, município, NCM, CST, cClassTrib, unidade p/ monofásico) e
     consulta a calculadora uma vez por combinação, com base de referência alta.
     O resultado (alíquotas efetivas e ad rem) fica em cache (calc_aliquotas),
     versionado pela versão da calculadora. As regras C001..C004 aplicam essas
     alíquotas a todos os itens via SQL.
  2. Amostra: recalcula itens reais completos (base e quantidade reais) e compara
     com o atalho (regra C007), validando a premissa de que a alíquota depende
     só daquela combinação.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyarrow as pa

from auditoria_rt.calc.base import BASE_REF, QTD_REF, Calculadora, ParametroCalculo, ResultadoCalculo
from auditoria_rt.workspace import Workspace

log = logging.getLogger(__name__)


def criar_calculadora(ws: Workspace) -> Calculadora:
    c = ws.cfg["calculadora"]
    if c.get("modo") == "http":
        from auditoria_rt.calc.http import CalculadoraHTTP
        calc = CalculadoraHTTP(c)
    else:
        from auditoria_rt.calc.tabela import CalculadoraTabela
        calc = CalculadoraTabela(ws.con, ws.versao_calculadora())
    return calc


def _agrupar(params: list[ParametroCalculo], tamanho: int) -> list[list[ParametroCalculo]]:
    grupos: dict[tuple, list] = defaultdict(list)
    for p in params:
        grupos[(p.data, p.uf, p.c_mun)].append(p)
    out = []
    for g in grupos.values():
        for i in range(0, len(g), tamanho):
            out.append(g[i:i + tamanho])
    return out


def _executar(calc: Calculadora, params: list[ParametroCalculo], cfg: dict, rotulo: str):
    grupos = _agrupar(params, int(cfg.get("itens_por_requisicao", 100)))
    workers = int(cfg.get("workers", 8)) if cfg.get("modo") == "http" else 1
    log.info("%s: %d parâmetros em %d requisições (%d workers)", rotulo, len(params), len(grupos), workers)
    feitos = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(calc.calcular, g) for g in grupos]
        for k, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            feitos += len(res)
            if k % 200 == 0:
                log.info("%s: %d/%d requisições", rotulo, k, len(grupos))
            yield res


def calcular_aliquotas(ws: Workspace, calc: Calculadora) -> dict:
    """Etapa 1: preenche o cache calc_aliquotas para as combinações ainda não calculadas."""
    versao = ws.versao_calculadora()
    pendentes = ws.con.execute("""
        SELECT DISTINCT i.dt_calc, i.uf_calc, i.c_mun_calc, coalesce(i.ncm, ''), i.cst,
                        coalesce(i.cclasstrib, ''), i.u_trib_calc
        FROM itens i
        WHERE i.ibscbs_presente AND i.cst IS NOT NULL AND i.dt_calc IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM calc_aliquotas c
            WHERE c.versao_calculadora = ? AND c.dt_calc = i.dt_calc AND c.uf = i.uf_calc
              AND c.c_mun = i.c_mun_calc AND c.ncm = coalesce(i.ncm, '') AND c.cst = i.cst
              AND c.cclasstrib = coalesce(i.cclasstrib, '') AND c.u_trib = i.u_trib_calc)
    """, [versao]).fetchall()
    total = ws.con.execute("SELECT count(*) FROM calc_aliquotas WHERE versao_calculadora = ?", [versao]).fetchall()[0][0]
    resumo = {"versao": versao, "em_cache": total, "pendentes": len(pendentes), "ok": 0, "erro": 0, "falha": 0}
    if not pendentes:
        return resumo
    params = [ParametroCalculo(data=d, uf=uf, c_mun=mun, ncm=ncm, cst=cst, cclasstrib=cc, u_trib=ut,
                               base=BASE_REF, quantidade=QTD_REF, ref=(d, uf, mun, ncm, cst, cc, ut))
              for d, uf, mun, ncm, cst, cc, ut in pendentes]
    for res in _executar(calc, params, ws.cfg["calculadora"], "Calculadora (atalho)"):
        linhas = []
        for r in res:
            if r.status == "FALHA":       # indisponibilidade: não grava no cache, tenta de novo depois
                resumo["falha"] += 1
                continue
            resumo["ok" if r.status == "OK" else "erro"] += 1
            linhas.append(_linha_cache(versao, r))
        _inserir(ws, "calc_aliquotas", linhas)
    return resumo


def _pct(v: float | None, base: float) -> float | None:
    return None if v is None else v / base * 100


def _linha_cache(versao: str, r: ResultadoCalculo) -> dict:
    d, uf, mun, ncm, cst, cc, ut = r.ref
    return {
        "versao_calculadora": versao, "dt_calc": d, "uf": uf, "c_mun": mun, "ncm": ncm, "cst": cst,
        "cclasstrib": cc, "u_trib": ut, "status": r.status, "mensagem": r.mensagem,
        "p_ibs_uf": r.p_ibs_uf, "p_ibs_mun": r.p_ibs_mun, "p_cbs": r.p_cbs,
        "aliq_efet_ibs_uf": _pct(r.v_ibs_uf, BASE_REF),
        "aliq_efet_ibs_mun": _pct(r.v_ibs_mun, BASE_REF),
        "aliq_efet_cbs": _pct(r.v_cbs, BASE_REF),
        "ad_rem_ibs": None if r.v_ibs_mono is None else r.v_ibs_mono / QTD_REF,
        "ad_rem_cbs": None if r.v_cbs_mono is None else r.v_cbs_mono / QTD_REF,
        "resposta": r.resposta,
    }


_CACHE_SCHEMA = pa.schema([
    ("versao_calculadora", pa.string()), ("dt_calc", pa.date32()), ("uf", pa.string()), ("c_mun", pa.string()),
    ("ncm", pa.string()), ("cst", pa.string()), ("cclasstrib", pa.string()), ("u_trib", pa.string()),
    ("status", pa.string()), ("mensagem", pa.string()),
    ("p_ibs_uf", pa.float64()), ("p_ibs_mun", pa.float64()), ("p_cbs", pa.float64()),
    ("aliq_efet_ibs_uf", pa.float64()), ("aliq_efet_ibs_mun", pa.float64()), ("aliq_efet_cbs", pa.float64()),
    ("ad_rem_ibs", pa.float64()), ("ad_rem_cbs", pa.float64()), ("resposta", pa.string()),
])

_AMOSTRA_SCHEMA = pa.schema([
    ("execucao", pa.string()), ("versao_calculadora", pa.string()), ("chave", pa.string()), ("n_item", pa.int32()),
    ("status", pa.string()), ("mensagem", pa.string()),
    ("v_ibs_uf", pa.float64()), ("v_ibs_mun", pa.float64()), ("v_cbs", pa.float64()), ("resposta", pa.string()),
])


def _inserir(ws: Workspace, tabela: str, linhas: list[dict]) -> None:
    if not linhas:
        return
    sch = _CACHE_SCHEMA if tabela == "calc_aliquotas" else _AMOSTRA_SCHEMA
    ws.con.register("_lote_tmp", pa.Table.from_pylist(linhas, schema=sch))
    cols = ", ".join(sch.names)
    extra = ", now()" if tabela == "calc_aliquotas" else ""
    ws.con.execute(f"INSERT INTO {tabela} SELECT {cols}{extra} FROM _lote_tmp")
    ws.con.unregister("_lote_tmp")


def calcular_amostra(ws: Workspace, calc: Calculadora, execucao: str) -> dict:
    """Etapa 2: cálculo completo de uma amostra aleatória reprodutível (regra C007)."""
    a = ws.cfg["amostra"]
    n, semente = int(a.get("tamanho", 0)), int(a.get("semente", 42))
    if n <= 0:
        return {"amostra": 0}
    versao = ws.versao_calculadora()
    ws.con.execute("DELETE FROM calc_amostra WHERE execucao = ?", [execucao])
    linhas = ws.con.execute(f"""
        SELECT chave, n_item, dt_emi, uf_calc, c_mun_calc, coalesce(ncm, ''), cst, coalesce(cclasstrib, ''),
               u_trib_calc, coalesce(v_bc, 0), coalesce(q_bc_mono, q_trib, 0)
        FROM (SELECT * FROM itens WHERE ibscbs_presente AND cst IS NOT NULL AND v_bc IS NOT NULL)
        USING SAMPLE reservoir({n} ROWS) REPEATABLE ({semente})
    """).fetchall()
    params = [ParametroCalculo(data=d, uf=uf, c_mun=mun, ncm=ncm, cst=cst, cclasstrib=cc, u_trib=ut,
                               base=float(vbc), quantidade=float(q or 0), ref=(ch, ni))
              for ch, ni, d, uf, mun, ncm, cst, cc, ut, vbc, q in linhas]
    resumo = {"amostra": len(params), "ok": 0, "erro": 0}
    for res in _executar(calc, params, ws.cfg["calculadora"], "Calculadora (amostra)"):
        out = []
        for r in res:
            resumo["ok" if r.status == "OK" else "erro"] += 1
            out.append({"execucao": execucao, "versao_calculadora": versao, "chave": r.ref[0], "n_item": r.ref[1],
                        "status": r.status, "mensagem": r.mensagem, "v_ibs_uf": r.v_ibs_uf,
                        "v_ibs_mun": r.v_ibs_mun, "v_cbs": r.v_cbs, "resposta": r.resposta})
        _inserir(ws, "calc_amostra", out)
    return resumo
