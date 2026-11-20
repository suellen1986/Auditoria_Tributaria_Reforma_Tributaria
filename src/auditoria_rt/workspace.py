"""Workspace: diretórios de dados + banco DuckDB (referências, cache, desvios).

Estrutura:
  <workdir>/raw/fonte=<f>/dt=<d>/part-*.parquet       XML bruto extraído do SAP
  <workdir>/parsed/{notas,itens,erros}/...              dados normalizados
  <workdir>/auditoria.duckdb                            referências, cache da calculadora, desvios
  <workdir>/saidas/<execucao>/                          relatório, desvios, manifesto
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path

import duckdb
import pyarrow as pa

from auditoria_rt.parse.esquema import SCHEMA_ERRO, SCHEMA_ITEM, SCHEMA_NOTA

log = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS ref_class_trib (
    cst VARCHAR, desc_cst VARCHAR, cclasstrib VARCHAR, desc_cclasstrib VARCHAR,
    p_red_ibs DOUBLE, p_red_cbs DOUBLE,
    g_red VARCHAR, g_dif VARCHAR, g_mono VARCHAR, g_trib_regular VARCHAR, g_cred_pres VARCHAR,
    ini_vigencia DATE, fim_vigencia DATE, origem VARCHAR
);
CREATE TABLE IF NOT EXISTS ref_aliquotas (
    tributo VARCHAR, uf VARCHAR, c_mun VARCHAR, ini_vigencia DATE, fim_vigencia DATE,
    aliquota DOUBLE, origem VARCHAR
);
CREATE TABLE IF NOT EXISTS ref_matriz (
    ncm_prefixo VARCHAR, cfop VARCHAR, tp_nf VARCHAR, cst_esperado VARCHAR,
    cclasstrib_esperado VARCHAR, observacao VARCHAR
);
CREATE TABLE IF NOT EXISTS ref_versoes (
    tabela VARCHAR, arquivo VARCHAR, sha256 VARCHAR, linhas BIGINT, carregado_em TIMESTAMP
);
CREATE TABLE IF NOT EXISTS calc_aliquotas (
    versao_calculadora VARCHAR, dt_calc DATE, uf VARCHAR, c_mun VARCHAR, ncm VARCHAR,
    cst VARCHAR, cclasstrib VARCHAR, u_trib VARCHAR,
    status VARCHAR, mensagem VARCHAR,
    p_ibs_uf DOUBLE, p_ibs_mun DOUBLE, p_cbs DOUBLE,
    aliq_efet_ibs_uf DOUBLE, aliq_efet_ibs_mun DOUBLE, aliq_efet_cbs DOUBLE,
    ad_rem_ibs DOUBLE, ad_rem_cbs DOUBLE,
    resposta VARCHAR, calculado_em TIMESTAMP
);
CREATE TABLE IF NOT EXISTS calc_amostra (
    execucao VARCHAR, versao_calculadora VARCHAR, chave VARCHAR, n_item INTEGER,
    status VARCHAR, mensagem VARCHAR,
    v_ibs_uf DOUBLE, v_ibs_mun DOUBLE, v_cbs DOUBLE, resposta VARCHAR
);
CREATE TABLE IF NOT EXISTS desvios (
    execucao VARCHAR, regra VARCHAR, severidade VARCHAR, bloco VARCHAR,
    chave VARCHAR, n_item INTEGER, campo VARCHAR,
    valor_declarado DOUBLE, valor_esperado DOUBLE, diferenca DOUBLE, impacto DOUBLE,
    detalhe VARCHAR
);
CREATE TABLE IF NOT EXISTS execucoes (
    execucao VARCHAR, inicio TIMESTAMP, fim TIMESTAMP, periodo_de DATE, periodo_ate DATE,
    versao_calculadora VARCHAR, config_hash VARCHAR, status VARCHAR, resumo VARCHAR
);
CREATE TABLE IF NOT EXISTS execucao_regras (
    execucao VARCHAR, regra VARCHAR, status VARCHAR, qtd BIGINT, segundos DOUBLE, mensagem VARCHAR
);
"""


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


class Workspace:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        w = cfg["workspace"]
        self.dir = Path(w["diretorio"]).resolve()
        self.dir_raw = self.dir / "raw"
        self.dir_parsed = self.dir / "parsed"
        self.dir_saidas = self.dir / "saidas"
        for d in (self.dir_raw, self.dir_parsed, self.dir_saidas):
            d.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.dir / "auditoria.duckdb"))
        self.con.execute(f"SET threads = {int(w.get('duckdb_threads', 4))}")
        self.con.execute(f"SET memory_limit = '{w.get('duckdb_memoria', '4GB')}'")
        self.con.execute(DDL)

    def fechar(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ refs
    def carregar_referencias(self) -> dict:
        r = self.cfg["referencias"]
        resumo = {}
        specs = {
            "ref_class_trib": (r["classificacao_tributaria"], """
                SELECT lpad(trim(cst), 3, '0'), desc_cst, lpad(trim(cclasstrib), 6, '0'), desc_cclasstrib,
                       TRY_CAST(nullif(p_red_ibs, '') AS DOUBLE), TRY_CAST(nullif(p_red_cbs, '') AS DOUBLE),
                       upper(coalesce(nullif(g_red, ''), 'PERMITIDO')), upper(coalesce(nullif(g_dif, ''), 'PERMITIDO')),
                       upper(coalesce(nullif(g_mono, ''), 'PERMITIDO')), upper(coalesce(nullif(g_trib_regular, ''), 'PERMITIDO')),
                       upper(coalesce(nullif(g_cred_pres, ''), 'PERMITIDO')),
                       TRY_CAST(nullif(ini_vigencia, '') AS DATE), TRY_CAST(nullif(fim_vigencia, '') AS DATE), origem
                FROM src"""),
            "ref_aliquotas": (r["aliquotas"], """
                SELECT upper(trim(tributo)), coalesce(nullif(trim(uf), ''), '*'), coalesce(nullif(trim(c_mun), ''), '*'),
                       CAST(ini_vigencia AS DATE), TRY_CAST(nullif(fim_vigencia, '') AS DATE),
                       CAST(aliquota AS DOUBLE), origem
                FROM src"""),
            "ref_matriz": (r["matriz_expectativa"], """
                SELECT trim(ncm_prefixo), coalesce(nullif(trim(cfop), ''), '*'), coalesce(nullif(trim(tp_nf), ''), '*'),
                       lpad(trim(cst_esperado), 3, '0'),
                       CASE WHEN nullif(trim(cclasstrib_esperado), '') IS NULL THEN NULL
                            ELSE lpad(trim(cclasstrib_esperado), 6, '0') END,
                       observacao
                FROM src"""),
        }
        for tabela, (caminho, select) in specs.items():
            if not caminho or not Path(caminho).exists():
                log.warning("Referência %s não encontrada (%s); tabela ficará vazia", tabela, caminho)
                self.con.execute(f"DELETE FROM {tabela}")
                continue
            p = Path(caminho)
            self.con.execute(f"DELETE FROM {tabela}")
            self.con.execute(
                f"INSERT INTO {tabela} WITH src AS (SELECT * FROM read_csv(?, header=true, all_varchar=true)) {select}",
                [str(p)],
            )
            n = self.con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]
            self.con.execute("DELETE FROM ref_versoes WHERE tabela = ?", [tabela])
            self.con.execute("INSERT INTO ref_versoes VALUES (?, ?, ?, ?, now())",
                             [tabela, str(p), sha256_arquivo(p), n])
            resumo[tabela] = n
            log.info("Referência %s carregada: %d linhas", tabela, n)
        exemplos = self.con.execute("SELECT count(*) FROM ref_class_trib WHERE origem = 'EXEMPLO'").fetchall()[0][0]
        if exemplos:
            log.warning("ATENÇÃO: ref_class_trib contém %d linhas de EXEMPLO. "
                        "Substitua pela tabela oficial de cClassTrib antes de auditar.", exemplos)
        return resumo

    # ----------------------------------------------------------------- views
    def _view_parquet(self, nome: str, subdir: str, sch: pa.Schema) -> None:
        base = self.dir_parsed / subdir
        if base.exists() and any(base.rglob("*.parquet")):
            glob = (base / "**" / "*.parquet").as_posix()
            self.con.execute(
                f"CREATE OR REPLACE TEMP VIEW {nome} AS "
                f"SELECT * FROM read_parquet('{glob}', hive_partitioning = false, union_by_name = true)"
            )
        else:
            self.con.register("_vazio_tmp", pa.Table.from_pylist([], schema=sch))
            self.con.execute(f"CREATE OR REPLACE TEMP TABLE {nome}_vazio AS SELECT * FROM _vazio_tmp")
            self.con.unregister("_vazio_tmp")
            self.con.execute(f"CREATE OR REPLACE TEMP VIEW {nome} AS SELECT * FROM {nome}_vazio")

    def criar_views(self, de: dt.date | None = None, ate: dt.date | None = None) -> None:
        """Views temporárias usadas pelas regras, calculadora e relatório."""
        self._view_parquet("notas_base", "notas", SCHEMA_NOTA)
        self._view_parquet("itens_base", "itens", SCHEMA_ITEM)
        self._view_parquet("erros_base", "erros", SCHEMA_ERRO)
        filtro = "TRUE"
        filtro_erro = "TRUE"
        if de:
            filtro += f" AND dt_emi >= DATE '{de.isoformat()}'"
            filtro_erro += f" AND dt_ref >= DATE '{de.isoformat()}'"
        if ate:
            filtro += f" AND dt_emi <= DATE '{ate.isoformat()}'"
            filtro_erro += f" AND dt_ref <= DATE '{ate.isoformat()}'"

        gran = self.cfg["calculadora"].get("granularidade_data", "mes")
        dt_calc = "date_trunc('month', dt_emi)::DATE" if gran == "mes" else "dt_emi"
        # notas_todas: sem deduplicação (usada pela R019). notas/itens: uma cópia por chave
        # (mesmo critério de escolha nas duas views, para não inflar somas e desvios).
        self.con.execute(f"CREATE OR REPLACE TEMP VIEW notas_todas AS SELECT * FROM notas_base WHERE {filtro}")
        self.con.execute("""
            CREATE OR REPLACE TEMP VIEW notas AS SELECT * FROM notas_todas
            QUALIFY row_number() OVER (PARTITION BY chave ORDER BY fonte, hash_xml, lote) = 1
        """)
        self.con.execute(f"CREATE OR REPLACE TEMP VIEW erros AS SELECT * FROM erros_base WHERE {filtro_erro}")
        # Local da operação para IBS (premissa P-03 em docs/premissas.md)
        self.con.execute(f"""
            CREATE OR REPLACE TEMP VIEW itens AS
            SELECT *,
                   coalesce(nullif(uf_entrega, ''), nullif(uf_dest, ''), uf_emit, '') AS uf_calc,
                   coalesce(nullif(c_mun_fg_ibs, ''), nullif(c_mun_entrega, ''), nullif(c_mun_dest, ''),
                            nullif(c_mun_fg, ''), '') AS c_mun_calc,
                   {dt_calc} AS dt_calc,
                   CASE WHEN tem_mono THEN upper(coalesce(u_trib, '')) ELSE '' END AS u_trib_calc
            FROM itens_base WHERE {filtro}
            QUALIFY row_number() OVER (PARTITION BY chave, n_item ORDER BY fonte, hash_xml, lote) = 1
        """)
        versao = self.versao_calculadora()
        self.con.execute(f"""
            CREATE OR REPLACE TEMP VIEW itens_calc AS
            SELECT i.*, c.status AS calc_status, c.mensagem AS calc_mensagem,
                   c.aliq_efet_ibs_uf AS calc_aliq_ibs_uf, c.aliq_efet_ibs_mun AS calc_aliq_ibs_mun,
                   c.aliq_efet_cbs AS calc_aliq_cbs, c.ad_rem_ibs AS calc_ad_rem_ibs, c.ad_rem_cbs AS calc_ad_rem_cbs
            FROM itens i
            LEFT JOIN calc_aliquotas c
              ON c.versao_calculadora = '{versao.replace("'", "''")}'
             AND c.dt_calc = i.dt_calc AND c.uf = i.uf_calc AND c.c_mun = i.c_mun_calc
             AND c.ncm = coalesce(i.ncm, '') AND c.cst = i.cst AND c.cclasstrib = coalesce(i.cclasstrib, '')
             AND c.u_trib = i.u_trib_calc
            WHERE i.ibscbs_presente
        """)

    def versao_calculadora(self) -> str:
        c = self.cfg["calculadora"]
        if c.get("modo") == "tabela":
            h = self.con.execute(
                "SELECT string_agg(sha256, '' ORDER BY tabela) FROM ref_versoes "
                "WHERE tabela IN ('ref_aliquotas', 'ref_class_trib')").fetchall()[0][0] or ""
            return "tabela-" + hashlib.sha256(h.encode()).hexdigest()[:12]
        return str(c.get("versao") or "nao-informada")
