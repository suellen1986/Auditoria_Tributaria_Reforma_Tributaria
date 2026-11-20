"""Extração SQL com banco falso (SQLite, mesmo paramstyle '?' do hdbcli/pyodbc)."""

import datetime as dt
import gzip
import sqlite3

import pyarrow.parquet as pq

from auditoria_rt.extract.base import extrair
from auditoria_rt.extract.sql import FonteSQL
from auditoria_rt.sintetico import NotaSint, chave_sintetica, gerar_xml


class FonteSQLite(FonteSQL):
    def __init__(self, caminho, **kw):
        cfg = {"nome": "sqlite", "tabela": "XML_NFE", "formato_data": "dats", "codificacao_xml": "auto",
               "colunas": {"chave": "CHAVE", "data": "DATA", "xml": "XML", "sequencia": kw.get("seq")}}
        super().__init__(cfg, {"linhas_por_lote": 2})
        self.caminho = caminho

    def conectar(self):
        return sqlite3.connect(self.caminho)


def test_extracao_dats_e_segmentos(tmp_path):
    db = tmp_path / "sap.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE XML_NFE (CHAVE TEXT, DATA TEXT, XML BLOB, SEQ INT)")
    xmls = {}
    for n in range(1, 6):
        ch = chave_sintetica(n)
        xml = gerar_xml(NotaSint(ch)).encode()
        xmls[ch] = xml
        comp = gzip.compress(xml)
        meio = len(comp) // 2
        con.execute("INSERT INTO XML_NFE VALUES (?, ?, ?, 1)", (ch, "20260310", comp[:meio]))
        con.execute("INSERT INTO XML_NFE VALUES (?, ?, ?, 2)", (ch, "20260310", comp[meio:]))
    con.execute("INSERT INTO XML_NFE VALUES ('OUTRO', '20260311', X'00', 1)")
    con.commit()
    con.close()

    fonte = FonteSQLite(str(db), seq="SEQ")
    assert "ORDER BY CHAVE, SEQ" in fonte.montar_sql()
    res = extrair([fonte], dt.date(2026, 3, 10), dt.date(2026, 3, 10), tmp_path / "raw", 1, 100, "t")
    assert res["xmls"] == 5 and not res["falhas"]
    tab = pq.read_table(next((tmp_path / "raw").rglob("*.parquet"))).to_pylist()
    assert {r["chave_origem"]: r["xml"] for r in tab} == xmls
    # retomada: segunda execução pula o dia
    assert extrair([fonte], dt.date(2026, 3, 10), dt.date(2026, 3, 10), tmp_path / "raw", 1, 100, "t")["puladas"] == 1
