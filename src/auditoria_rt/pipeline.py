"""Etapas do processo, usadas pela CLI. Cada etapa é idempotente e pode ser rodada isoladamente."""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid

from auditoria_rt.calc.orquestrador import calcular_aliquotas, calcular_amostra, criar_calculadora
from auditoria_rt.extract import criar_fonte
from auditoria_rt.extract.base import extrair
from auditoria_rt.parse.executor import processar
from auditoria_rt.report.excel import gerar
from auditoria_rt.rules import base as regras
from auditoria_rt.workspace import Workspace

log = logging.getLogger(__name__)


def nova_execucao() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def etapa_referencias(ws: Workspace) -> dict:
    return ws.carregar_referencias()


def etapa_extrair(ws: Workspace, de: dt.date, ate: dt.date, refazer: bool = False, lote: str | None = None) -> dict:
    cfg = ws.cfg["extracao"]
    fontes = [criar_fonte(f, cfg) for f in cfg.get("fontes", [])]
    if not fontes:
        raise ValueError("Nenhuma fonte configurada em extracao.fontes")
    return extrair(fontes, de, ate, ws.dir_raw, int(cfg.get("paralelismo", 1)),
                   int(cfg.get("linhas_por_arquivo", 50000)), lote or nova_execucao(), refazer)


def etapa_processar(ws: Workspace, workers: int | None = None, refazer: bool = False) -> dict:
    return processar(ws.dir_raw, ws.dir_parsed, workers, refazer)


def etapa_calcular(ws: Workspace, execucao: str, de=None, ate=None, amostra: bool = True) -> dict:
    ws.criar_views(de, ate)
    calc = criar_calculadora(ws)
    res = {"aliquotas": calcular_aliquotas(ws, calc)}
    if amostra:
        res["amostra"] = calcular_amostra(ws, calc, execucao)
    return res


def etapa_auditar(ws: Workspace, execucao: str, de=None, ate=None, somente=None) -> list[dict]:
    ws.criar_views(de, ate)
    return regras.executar(ws, ws.cfg, execucao, somente)


def etapa_relatorio(ws: Workspace, execucao: str, de=None, ate=None, extras=None):
    ws.criar_views(de, ate)
    return gerar(ws, execucao, (de, ate), extras)


def executar_tudo(ws: Workspace, de: dt.date, ate: dt.date, extrair_sap: bool = True,
                  workers: int | None = None) -> dict:
    execucao = nova_execucao()
    inicio = dt.datetime.now()
    resumo: dict = {"execucao": execucao}
    status = "OK"
    try:
        resumo["referencias"] = etapa_referencias(ws)
        if extrair_sap:
            resumo["extracao"] = etapa_extrair(ws, de, ate, lote=execucao)
        resumo["processamento"] = etapa_processar(ws, workers)
        resumo["calculo"] = etapa_calcular(ws, execucao, de, ate)
        resumo["regras"] = etapa_auditar(ws, execucao, de, ate)
        resumo["relatorio"] = str(etapa_relatorio(ws, execucao, de, ate,
                                                  {"etapas": {k: v for k, v in resumo.items() if k != "regras"}}))
    except Exception:
        status = "ERRO"
        raise
    finally:
        ws.con.execute("INSERT INTO execucoes VALUES (?, ?, now(), ?, ?, ?, ?, ?, ?)",
                       [execucao, inicio, de, ate, ws.versao_calculadora(), ws.cfg.hash, status,
                        json.dumps(resumo, default=str)[:100000]])
    return resumo
