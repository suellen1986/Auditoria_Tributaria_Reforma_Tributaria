"""Calculadora por tabela (sem a calculadora da RFB).

Usa as alíquotas de referência (config/referencia/aliquotas_referencia.csv) e os
percentuais de redução da tabela de classificação tributária. Serve para:
  * rodar o pipeline completo no primeiro dia, antes de a calculadora estar no ar;
  * testes automatizados;
  * contraprova independente da calculadora.
Não trata monofásico (ad rem) nem regras específicas: para isso use o modo http.
"""

from __future__ import annotations

import datetime as dt

import duckdb

from auditoria_rt.calc.base import Calculadora, ParametroCalculo, ResultadoCalculo


class CalculadoraTabela(Calculadora):
    def __init__(self, con: duckdb.DuckDBPyConnection, versao: str):
        self.versao = versao
        self.aliq = con.execute(
            "SELECT tributo, uf, c_mun, ini_vigencia, coalesce(fim_vigencia, DATE '9999-12-31'), aliquota "
            "FROM ref_aliquotas").fetchall()
        self.red = {
            (cst, cc): (pi or 0.0, pc or 0.0)
            for cst, cc, pi, pc in con.execute(
                "SELECT cst, cclasstrib, p_red_ibs, p_red_cbs FROM ref_class_trib").fetchall()
        }

    def _aliquota(self, tributo: str, data: dt.date, uf: str, mun: str) -> float | None:
        melhor, nota = None, -1
        for t, a_uf, a_mun, ini, fim, val in self.aliq:
            if t != tributo or not (ini <= data <= fim):
                continue
            if a_uf not in ("*", uf) or a_mun not in ("*", mun):
                continue
            esp = (a_uf != "*") + 2 * (a_mun != "*")
            if esp > nota:
                melhor, nota = val, esp
        return melhor

    def calcular(self, params: list[ParametroCalculo]) -> list[ResultadoCalculo]:
        out = []
        for p in params:
            red = self.red.get((p.cst, p.cclasstrib))
            if red is None:
                out.append(ResultadoCalculo(ref=p.ref, status="ERRO",
                                            mensagem=f"CST/cClassTrib {p.cst}/{p.cclasstrib} não encontrado na tabela"))
                continue
            a_uf = self._aliquota("IBS_UF", p.data, p.uf, p.c_mun)
            a_mun = self._aliquota("IBS_MUN", p.data, p.uf, p.c_mun)
            a_cbs = self._aliquota("CBS", p.data, p.uf, p.c_mun)
            if a_cbs is None and a_uf is None:
                out.append(ResultadoCalculo(ref=p.ref, status="ERRO",
                                            mensagem=f"Sem alíquota de referência vigente em {p.data}"))
                continue
            f_ibs, f_cbs = 1 - red[0] / 100, 1 - red[1] / 100
            e_uf, e_mun, e_cbs = (a_uf or 0) * f_ibs, (a_mun or 0) * f_ibs, (a_cbs or 0) * f_cbs
            out.append(ResultadoCalculo(
                ref=p.ref, p_ibs_uf=a_uf, p_ibs_mun=a_mun, p_cbs=a_cbs,
                v_ibs_uf=round(p.base * e_uf / 100, 2),
                v_ibs_mun=round(p.base * e_mun / 100, 2),
                v_cbs=round(p.base * e_cbs / 100, 2),
            ))
        return out

    def testar(self) -> str:
        return f"modo tabela: {len(self.aliq)} alíquotas, {len(self.red)} classificações"
