"""Fontes SQL: SAP HANA (hdbcli) e ODBC genérico (camada de virtualização).

A consulta é montada a partir da configuração e parametrizada pela data, para
extrair um dia por vez (permite paralelismo e retomada).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Iterator

from auditoria_rt.extract.base import Fonte

log = logging.getLogger(__name__)

_IDENT = re.compile(r'^[A-Za-z0-9_"./:]+$')


def _ident(nome: str, campo: str) -> str:
    """Valida identificadores vindos da configuração (evita SQL injection acidental)."""
    if not nome or not _IDENT.match(nome):
        raise ValueError(f"Identificador inválido em {campo}: {nome!r}")
    return nome


class FonteSQL(Fonte):
    def __init__(self, cfg_fonte: dict, cfg_extracao: dict):
        super().__init__(cfg_fonte, cfg_extracao)
        col = cfg_fonte["colunas"]
        self.tabela = _ident(cfg_fonte["tabela"], "tabela")
        self.c_chave = _ident(col["chave"], "colunas.chave")
        self.c_data = _ident(col["data"], "colunas.data")
        self.c_xml = _ident(col["xml"], "colunas.xml")
        self.c_seq = _ident(col["sequencia"], "colunas.sequencia") if col.get("sequencia") else None
        self.formato_data = cfg_fonte.get("formato_data", "date")
        self.filtro = cfg_fonte.get("filtro_extra") or ""

    # -- conexão -------------------------------------------------------------
    def conectar(self):  # pragma: no cover - depende do driver
        raise NotImplementedError

    # -- consulta ------------------------------------------------------------
    def _limites(self, dia: dt.date):
        prox = dia + dt.timedelta(days=1)
        if self.formato_data == "date":
            return dia, prox
        if self.formato_data == "dats":
            return dia.strftime("%Y%m%d"), prox.strftime("%Y%m%d")
        if self.formato_data == "timestamp_dec":
            return int(dia.strftime("%Y%m%d000000")), int(prox.strftime("%Y%m%d000000"))
        raise ValueError(f"formato_data desconhecido: {self.formato_data}")

    def montar_sql(self) -> str:
        cols = f"{self.c_chave}, {self.c_data}, {self.c_xml}"
        ordem = ""
        if self.c_seq:
            cols += f", {self.c_seq}"
            ordem = f" ORDER BY {self.c_chave}, {self.c_seq}"
        return (f"SELECT {cols} FROM {self.tabela} "
                f"WHERE {self.c_data} >= ? AND {self.c_data} < ? {self.filtro}{ordem}")

    def ler_dia(self, dia: dt.date) -> Iterator[list[tuple]]:
        sql = self.montar_sql()
        con = self.conectar()
        try:
            cur = con.cursor()
            cur.execute(sql, self._limites(dia))
            if self.c_seq:
                yield from self._agrupar_sequencia(cur, dia)
                return
            while True:
                linhas = cur.fetchmany(self.linhas_por_lote)
                if not linhas:
                    break
                yield [(l[0], dia, l[2]) for l in linhas]
        finally:
            con.close()

    def _agrupar_sequencia(self, cur, dia) -> Iterator[list[tuple]]:
        """XML quebrado em várias linhas (ex.: segmentos RAW): concatena por chave."""
        atual, partes, saida = None, [], []
        while True:
            linhas = cur.fetchmany(self.linhas_por_lote)
            if not linhas:
                break
            for chave, _data, conteudo, _seq in linhas:
                if hasattr(conteudo, "read"):
                    conteudo = conteudo.read()
                if chave != atual and atual is not None:
                    saida.append((atual, dia, _juntar(partes)))
                    partes = []
                atual = chave
                partes.append(conteudo)
            if len(saida) >= self.linhas_por_lote:
                yield saida
                saida = []
        if atual is not None:
            saida.append((atual, dia, _juntar(partes)))
        if saida:
            yield saida

    def testar(self) -> str:
        con = self.conectar()
        try:
            cur = con.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self.tabela} WHERE 1=0")
            cur.fetchall()
            return f"conexão OK; tabela {self.tabela} acessível"
        finally:
            con.close()


def _juntar(partes: list) -> bytes | str:
    if all(isinstance(p, str) for p in partes):
        return "".join(partes)
    return b"".join(p.encode() if isinstance(p, str) else bytes(p) for p in partes)


class FonteHana(FonteSQL):
    def conectar(self):  # pragma: no cover - depende do ambiente
        from hdbcli import dbapi  # driver oficial SAP

        c = self.cfg["conexao"]
        return dbapi.connect(
            address=c["host"],
            port=int(c["porta"]),
            user=c["usuario"],
            password=c["senha"],
            encrypt=str(c.get("criptografar", True)).lower() == "true",
            sslValidateCertificate=str(c.get("validar_certificado", True)).lower() == "true",
        )


class FonteODBC(FonteSQL):
    def conectar(self):  # pragma: no cover - depende do ambiente
        import pyodbc

        return pyodbc.connect(self.cfg["conexao"]["odbc_dsn"], autocommit=True)
