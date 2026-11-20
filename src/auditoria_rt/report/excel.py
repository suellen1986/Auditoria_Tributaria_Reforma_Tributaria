"""Relatório para a Auditoria Interna (Excel) + detalhe completo (parquet/CSV) + manifesto."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import xlsxwriter

from auditoria_rt import __version__
from auditoria_rt.rules.base import todas
from auditoria_rt.workspace import Workspace

log = logging.getLogger(__name__)

ORDEM_SEV = "CASE severidade WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END"
LIMITE_EXCEL = 1_048_000


def _consultar(ws: Workspace, sql: str, params=None):
    cur = ws.con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def _aba(wb, nome: str, cols, linhas, fmt, larguras: dict | None = None, moeda: set | None = None):
    sh = wb.add_worksheet(nome[:31])
    sh.write_row(0, 0, cols, fmt["cab"])
    moeda = moeda or set()
    for i, linha in enumerate(linhas, 1):
        for j, v in enumerate(linha):
            if isinstance(v, (dt.date, dt.datetime)):
                sh.write_datetime(i, j, dt.datetime.combine(v, dt.time()) if type(v) is dt.date else v, fmt["data"])
            elif isinstance(v, float) and cols[j] in moeda:
                sh.write_number(i, j, v, fmt["moeda"])
            elif v is None:
                sh.write_blank(i, j, None)
            else:
                sh.write(i, j, v)
    sh.freeze_panes(1, 0)
    if linhas:
        sh.autofilter(0, 0, len(linhas), len(cols) - 1)
    for j, c in enumerate(cols):
        sh.set_column(j, j, (larguras or {}).get(c, max(12, min(45, len(c) + 4))))
    return sh


def gerar(ws: Workspace, execucao: str, periodo: tuple | None = None, extras: dict | None = None) -> Path:
    cfg = ws.cfg
    saida = ws.dir_saidas / execucao
    saida.mkdir(parents=True, exist_ok=True)
    catalogo = {r.id: r for r in todas()}

    # Catálogo de regras como tabela temporária para os joins do relatório
    ws.con.execute("CREATE OR REPLACE TEMP TABLE catalogo (regra VARCHAR, titulo VARCHAR, fundamento VARCHAR)")
    ws.con.executemany("INSERT INTO catalogo VALUES (?, ?, ?)", [(r.id, r.titulo, r.fundamento) for r in catalogo.values()])

    ws.con.execute("""
        CREATE OR REPLACE TEMP VIEW desvios_det AS
        SELECT d.*,
               -- impacto sem dupla contagem: maior impacto por (nota, item, campo) entre as regras financeiras
               CASE WHEN d.impacto IS NOT NULL AND row_number() OVER (
                        PARTITION BY d.chave, d.n_item, d.campo, d.impacto IS NOT NULL ORDER BY d.impacto DESC) = 1
                    THEN d.impacto END AS impacto_consolidado,
               c.titulo, n.dt_emi, n.n_nf, n.serie, n.tp_nf, n.cnpj_emit, n.x_nome_emit, n.uf_emit,
               n.cnpj_dest, n.x_nome_dest, n.uf_dest, i.ncm, i.cfop, i.c_prod, i.x_prod, i.cst, i.cclasstrib, i.v_bc
        FROM desvios d
        LEFT JOIN catalogo c ON c.regra = d.regra
        LEFT JOIN notas n
               ON n.chave = d.chave
        LEFT JOIN itens i
               ON i.chave = d.chave AND i.n_item = d.n_item
        WHERE d.execucao = ?
    """.replace("?", f"'{execucao}'"))

    # ---- detalhe completo (parquet e CSV) -----------------------------------
    arq_parquet = saida / "desvios_detalhe.parquet"
    ws.con.execute(f"COPY (SELECT * FROM desvios_det ORDER BY {ORDEM_SEV}, impacto DESC NULLS LAST) "
                   f"TO '{arq_parquet.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    if cfg["relatorio"].get("exportar_csv", True):
        arq_csv = saida / "desvios_detalhe.csv"
        ws.con.execute(f"COPY (SELECT * FROM desvios_det ORDER BY {ORDEM_SEV}, impacto DESC NULLS LAST) "
                       f"TO '{arq_csv.as_posix()}' (HEADER, DELIMITER ';')")

    # ---- números gerais -------------------------------------------------------
    tot = ws.con.execute("""
        SELECT (SELECT count(*) FROM notas), (SELECT count(*) FROM itens),
               (SELECT count(*) FROM itens WHERE ibscbs_presente), (SELECT count(*) FROM erros)
    """).fetchall()[0]
    n_desv, n_notas_desv, impacto = ws.con.execute(
        "SELECT count(*), count(DISTINCT chave), coalesce(sum(impacto_consolidado), 0) FROM desvios_det").fetchall()[0]
    refs = _consultar(ws, "SELECT tabela, arquivo, sha256, linhas, carregado_em FROM ref_versoes ORDER BY tabela")
    exemplos = ws.con.execute("SELECT count(*) FROM ref_class_trib WHERE origem = 'EXEMPLO'").fetchall()[0][0]

    manifesto = {
        "execucao": execucao,
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "software": f"auditoria-rt {__version__}",
        "periodo": [str(p) if p else None for p in (periodo or (None, None))],
        "versao_calculadora": ws.versao_calculadora(),
        "modo_calculadora": cfg["calculadora"].get("modo"),
        "config_hash": cfg.hash if hasattr(cfg, "hash") else None,
        "tolerancias": {k: cfg["regras"][k] for k in ("tolerancia_abs", "tolerancia_rel", "tolerancia_aliquota")},
        "referencias": [dict(zip(refs[0], [str(x) for x in r])) for r in refs[1]],
        "contagens": {"notas": tot[0], "itens": tot[1], "itens_com_ibscbs": tot[2], "xml_com_erro": tot[3],
                      "desvios": n_desv, "notas_com_desvio": n_notas_desv, "impacto_total": impacto},
        "alertas": (["Tabela de cClassTrib contém linhas de EXEMPLO - resultado não conclusivo"] if exemplos else []),
        **(extras or {}),
    }
    (saida / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # ---- Excel ------------------------------------------------------------------
    arq = saida / f"relatorio_auditoria_{execucao}.xlsx"
    wb = xlsxwriter.Workbook(arq, {"constant_memory": False, "strings_to_urls": False})
    fmt = {
        "cab": wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "#FFFFFF", "border": 1, "text_wrap": True}),
        "moeda": wb.add_format({"num_format": "#,##0.00"}),
        "data": wb.add_format({"num_format": "dd/mm/yyyy"}),
        "titulo": wb.add_format({"bold": True, "font_size": 14}),
        "neg": wb.add_format({"bold": True}),
        "alerta": wb.add_format({"bold": True, "font_color": "#C00000"}),
    }

    sh = wb.add_worksheet("Leia-me")
    sh.set_column(0, 0, 34)
    sh.set_column(1, 1, 90)
    sh.write(0, 0, "Auditoria IBS/CBS/IS - NF-e", fmt["titulo"])
    linhas_info = [
        ("Execução", execucao),
        ("Gerado em", manifesto["gerado_em"]),
        ("Período", f"{manifesto['periodo'][0]} a {manifesto['periodo'][1]}"),
        ("Software", manifesto["software"]),
        ("Calculadora", f"{manifesto['modo_calculadora']} - versão {manifesto['versao_calculadora']}"),
        ("Hash da configuração", str(manifesto["config_hash"])),
        ("Tolerâncias", json.dumps(manifesto["tolerancias"])),
        ("Notas auditadas", tot[0]),
        ("Itens auditados", tot[1]),
        ("Itens com IBSCBS", tot[2]),
        ("XMLs com erro de leitura", tot[3]),
        ("Desvios", n_desv),
        ("Notas com desvio", n_notas_desv),
        ("Impacto estimado (|diferença|, sem dupla contagem por item e campo)", impacto),
    ]
    for i, (k, v) in enumerate(linhas_info, 2):
        sh.write(i, 0, k, fmt["neg"])
        sh.write(i, 1, v, fmt["moeda"] if isinstance(v, float) else None)
    lin = len(linhas_info) + 3
    for a in manifesto["alertas"]:
        sh.write(lin, 0, "ALERTA", fmt["alerta"])
        sh.write(lin, 1, a, fmt["alerta"])
        lin += 1
    lin += 1
    sh.write(lin, 0, "Tabelas de referência", fmt["neg"])
    for r in refs[1]:
        lin += 1
        sh.write(lin, 0, r[0])
        sh.write(lin, 1, f"{r[1]} | sha256 {r[2][:16]}... | {r[3]} linhas")
    lin += 2
    sh.write(lin, 0, "Leitura", fmt["neg"])
    sh.write(lin, 1, "Cada linha de desvio = 1 regra violada em 1 item (ou nota). 'Esperado' é o valor recalculado; "
                     "'Diferença' = declarado - esperado. Detalhe completo em desvios_detalhe.parquet/.csv.")

    cols, dados = _consultar(ws, f"""
        SELECT d.regra AS "Regra", c.titulo AS "Título", d.bloco AS "Bloco", d.severidade AS "Severidade",
               count(*) AS "Desvios", count(DISTINCT d.chave) AS "Notas",
               round(sum(d.impacto), 2) AS "Impacto (R$)", c.fundamento AS "Fundamento"
        FROM desvios d LEFT JOIN catalogo c ON c.regra = d.regra
        WHERE d.execucao = '{execucao}'
        GROUP BY ALL ORDER BY min({ORDEM_SEV.replace('severidade', 'd.severidade')}), "Desvios" DESC
    """)
    _aba(wb, "Resumo por regra", cols, dados, fmt, {"Título": 55, "Fundamento": 60}, {"Impacto (R$)"})

    cols, dados = _consultar(ws, f"""
        SELECT r.id AS "Regra", r.status AS "Status execução", r.qtd AS "Desvios", round(r.segundos, 1) AS "Segundos",
               r.mensagem AS "Mensagem"
        FROM (SELECT regra AS id, status, qtd, segundos, mensagem FROM execucao_regras WHERE execucao = '{execucao}') r
        ORDER BY r.id
    """)
    _aba(wb, "Execução das regras", cols, dados, fmt, {"Mensagem": 80})

    cols, dados = _consultar(ws, f"""
        SELECT cnpj_emit AS "CNPJ emitente", any_value(x_nome_emit) AS "Emitente", any_value(uf_emit) AS "UF",
               count(*) AS "Desvios", count(DISTINCT chave) AS "Notas",
               count(*) FILTER (WHERE severidade = 'ALTA') AS "Alta",
               round(sum(impacto_consolidado), 2) AS "Impacto (R$)", mode(regra) AS "Regra mais frequente"
        FROM desvios_det GROUP BY cnpj_emit ORDER BY "Impacto (R$)" DESC NULLS LAST, "Desvios" DESC LIMIT 50000
    """)
    _aba(wb, "Por emitente", cols, dados, fmt, {"Emitente": 45}, {"Impacto (R$)"})

    cols, dados = _consultar(ws, f"""
        SELECT cnpj_dest AS "CNPJ destinatário", any_value(x_nome_dest) AS "Destinatário", any_value(uf_dest) AS "UF",
               count(*) AS "Desvios", count(DISTINCT chave) AS "Notas", round(sum(impacto_consolidado), 2) AS "Impacto (R$)",
               mode(regra) AS "Regra mais frequente"
        FROM desvios_det GROUP BY cnpj_dest ORDER BY "Impacto (R$)" DESC NULLS LAST, "Desvios" DESC LIMIT 50000
    """)
    _aba(wb, "Por destinatário", cols, dados, fmt, {"Destinatário": 45}, {"Impacto (R$)"})

    cols, dados = _consultar(ws, f"""
        SELECT ncm AS "NCM", any_value(x_prod) AS "Exemplo de produto", count(*) AS "Desvios",
               count(DISTINCT chave) AS "Notas", round(sum(impacto_consolidado), 2) AS "Impacto (R$)",
               string_agg(DISTINCT cst || '/' || coalesce(cclasstrib, ''), ', ') AS "CST/cClassTrib usados",
               mode(regra) AS "Regra mais frequente"
        FROM desvios_det WHERE ncm IS NOT NULL GROUP BY ncm ORDER BY "Impacto (R$)" DESC NULLS LAST, "Desvios" DESC LIMIT 50000
    """)
    _aba(wb, "Por NCM", cols, dados, fmt, {"Exemplo de produto": 45, "CST/cClassTrib usados": 40}, {"Impacto (R$)"})

    cols, dados = _consultar(ws, f"""
        SELECT strftime(date_trunc('month', dt_emi), '%Y-%m') AS "Mês", regra AS "Regra", count(*) AS "Desvios",
               count(DISTINCT chave) AS "Notas", round(sum(impacto), 2) AS "Impacto (R$)"
        FROM desvios_det GROUP BY ALL ORDER BY 1, 2
    """)
    _aba(wb, "Por mês", cols, dados, fmt, None, {"Impacto (R$)"})

    max_det = min(int(cfg["relatorio"].get("max_linhas_detalhe", 200000)), LIMITE_EXCEL)
    cols, dados = _consultar(ws, f"""
        SELECT severidade AS "Severidade", regra AS "Regra", titulo AS "Título", chave AS "Chave de acesso",
               n_item AS "Item", dt_emi AS "Emissão", n_nf AS "Número", cnpj_emit AS "CNPJ emitente",
               x_nome_emit AS "Emitente", cnpj_dest AS "CNPJ destinatário", ncm AS "NCM", cfop AS "CFOP",
               x_prod AS "Produto", cst AS "CST", cclasstrib AS "cClassTrib", campo AS "Campo",
               valor_declarado AS "Declarado", valor_esperado AS "Esperado", diferenca AS "Diferença",
               impacto AS "Impacto", detalhe AS "Detalhe"
        FROM desvios_det ORDER BY {ORDEM_SEV}, impacto DESC NULLS LAST LIMIT {max_det}
    """)
    _aba(wb, "Detalhe (top)", cols, dados, fmt,
         {"Chave de acesso": 48, "Título": 45, "Emitente": 35, "Produto": 35, "Detalhe": 70},
         {"Declarado", "Esperado", "Diferença", "Impacto"})

    cols = ["Regra", "Título", "Bloco", "Severidade padrão", "Financeira", "Descrição", "Fundamento"]
    dados = [(r.id, r.titulo, r.bloco, r.severidade, "Sim" if r.financeira else "Não", r.descricao, r.fundamento)
             for r in catalogo.values()]
    _aba(wb, "Catálogo de regras", cols, dados, fmt, {"Título": 45, "Descrição": 90, "Fundamento": 55})

    wb.close()
    log.info("Relatório gerado: %s", arq)
    return arq
