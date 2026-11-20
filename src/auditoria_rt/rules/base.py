"""Motor de regras.

Cada regra é uma consulta SQL (DuckDB) sobre as views `itens`, `notas`, `erros`,
`itens_calc` e as tabelas de referência. A consulta deve devolver as colunas:
    chave, n_item, campo, valor_declarado, valor_esperado, detalhe
Uma linha = um desvio. O motor grava em `desvios` com execução, severidade e bloco.

Parâmetros de configuração entram por substituição `$nome` (string.Template).
Macros disponíveis nas consultas:
    fora_tol(declarado, esperado)   -> diferença acima da tolerância monetária
    fora_tol_aliq(declarado, esperado) -> diferença acima da tolerância de alíquota
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from string import Template

from auditoria_rt.workspace import Workspace

log = logging.getLogger(__name__)

SEVERIDADES = ("ALTA", "MEDIA", "BAIXA", "INFO")


@dataclass(frozen=True)
class Regra:
    id: str
    titulo: str
    bloco: str                 # ESTRUTURA | CALCULO | PADRAO | EXPECTATIVA
    severidade: str
    descricao: str
    fundamento: str
    sql: str
    financeira: bool = False   # diferença representa valor de tributo (entra no impacto)
    requer: tuple = field(default_factory=tuple)


def parametros(cfg: dict, ws: Workspace, execucao: str = "") -> dict:
    r = cfg["regras"]
    comp = r.get("base_calculo", {})
    termos = [f"({float(peso)}) * coalesce({col}, 0)" for col, peso in comp.items() if float(peso) != 0]
    return {
        "obrig_desde": r.get("ibscbs_obrigatorio_desde", "2026-01-01"),
        "expr_base": " + ".join(termos) or "0",
        "min_itens_ncm": int(r.get("padroes", {}).get("min_itens_ncm", 50)),
        "limiar_minoritario": float(r.get("padroes", {}).get("limiar_minoritario", 0.02)),
        "versao": ws.versao_calculadora().replace("'", "''"),
        "execucao": execucao.replace("'", "''"),
    }


def criar_macros(ws: Workspace, cfg: dict) -> None:
    r = cfg["regras"]
    tol_abs, tol_rel = float(r.get("tolerancia_abs", 0.01)), float(r.get("tolerancia_rel", 0.0))
    tol_aliq = float(r.get("tolerancia_aliquota", 0.0001))
    # pequena folga numérica para não acusar diferença exatamente igual à tolerância
    ws.con.execute(f"""
        CREATE OR REPLACE TEMP MACRO fora_tol(d, e) AS
            abs(coalesce(d, 0) - coalesce(e, 0)) > greatest({tol_abs}, {tol_rel} * abs(coalesce(e, 0))) + 1e-9
    """)
    # classificação deduplicada (vigência mais recente) para joins das regras
    ws.con.execute("""
        CREATE OR REPLACE TEMP VIEW ref_ct AS
        SELECT * FROM ref_class_trib
        QUALIFY row_number() OVER (PARTITION BY cst, cclasstrib ORDER BY ini_vigencia DESC NULLS LAST) = 1
    """)
    ws.con.execute(f"""
        CREATE OR REPLACE TEMP MACRO fora_tol_aliq(d, e) AS
            abs(coalesce(d, 0) - coalesce(e, 0)) > {tol_aliq} + 1e-9
    """)


def todas() -> list[Regra]:
    from auditoria_rt.rules import calculo, estrutura, padroes
    regras = estrutura.REGRAS + calculo.REGRAS + padroes.REGRAS
    ids = [r.id for r in regras]
    assert len(ids) == len(set(ids)), "IDs de regra duplicados"
    return regras


def executar(ws: Workspace, cfg: dict, execucao: str, somente: list[str] | None = None) -> list[dict]:
    criar_macros(ws, cfg)
    params = parametros(cfg, ws, execucao)
    desab = set(cfg["regras"].get("desabilitadas") or [])
    sev_cfg = cfg["regras"].get("severidade") or {}
    ws.con.execute("DELETE FROM desvios WHERE execucao = ?", [execucao])
    ws.con.execute("DELETE FROM execucao_regras WHERE execucao = ?", [execucao])
    resultado = []
    for r in todas():
        if (somente and r.id not in somente) or r.id in desab:
            continue
        sev = sev_cfg.get(r.id, r.severidade)
        sql = Template(r.sql).substitute(params)
        t0 = time.perf_counter()
        try:
            ws.con.execute(f"""
                INSERT INTO desvios
                SELECT ?, ?, ?, ?, q.chave, q.n_item::INTEGER, q.campo,
                       q.valor_declarado::DOUBLE, q.valor_esperado::DOUBLE,
                       (q.valor_declarado - q.valor_esperado)::DOUBLE,
                       CASE WHEN ? THEN abs(coalesce(q.valor_declarado, 0) - coalesce(q.valor_esperado, 0)) END,
                       q.detalhe
                FROM ({sql}) q
            """, [execucao, r.id, sev, r.bloco, r.financeira])
            qtd = ws.con.execute("SELECT count(*) FROM desvios WHERE execucao = ? AND regra = ?",
                                 [execucao, r.id]).fetchall()[0][0]
            status, msg = "OK", None
        except Exception as e:  # uma regra com problema não derruba a execução
            log.exception("Regra %s falhou", r.id)
            qtd, status, msg = 0, "ERRO", str(e)[:1000]
        seg = time.perf_counter() - t0
        ws.con.execute("INSERT INTO execucao_regras VALUES (?, ?, ?, ?, ?, ?)", [execucao, r.id, status, qtd, seg, msg])
        log.info("Regra %-5s %-6s %8d desvios  (%.1fs)  %s", r.id, status, qtd, seg, r.titulo)
        resultado.append({"regra": r.id, "status": status, "qtd": qtd, "segundos": round(seg, 2), "mensagem": msg})
    return resultado
