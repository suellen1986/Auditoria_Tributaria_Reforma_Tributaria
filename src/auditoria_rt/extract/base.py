"""Contrato das fontes e gravação particionada (parquet por dia, retomável)."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from auditoria_rt.extract.decodificar import decodificar
from auditoria_rt.parse.esquema import SCHEMA_BRUTO

log = logging.getLogger(__name__)

MARCADOR = "_SUCCESS"


def dias(de: dt.date, ate: dt.date) -> list[dt.date]:
    return [de + dt.timedelta(days=i) for i in range((ate - de).days + 1)]


class Fonte(ABC):
    def __init__(self, cfg_fonte: dict, cfg_extracao: dict):
        self.cfg = cfg_fonte
        self.nome = cfg_fonte["nome"]
        self.codificacao = cfg_fonte.get("codificacao_xml", "auto")
        self.linhas_por_lote = int(cfg_extracao.get("linhas_por_lote", 5000))

    @abstractmethod
    def ler_dia(self, dia: dt.date) -> Iterator[list[tuple]]:
        """Gera lotes de (chave, data, xml_bruto) do dia informado."""

    def testar(self) -> str:
        return "ok"


class GravadorParticao:
    """Grava os XMLs de um dia em raw/fonte=<f>/dt=<d>/part-NNNNN.parquet."""

    def __init__(self, diretorio: Path, linhas_por_arquivo: int):
        self.dir = diretorio
        self.max = linhas_por_arquivo
        self.buf: list[dict] = []
        self.n_arq = 0
        self.total = 0
        self.dir.mkdir(parents=True, exist_ok=True)

    def adicionar(self, linha: dict) -> None:
        self.buf.append(linha)
        if len(self.buf) >= self.max:
            self._descarregar()

    def _descarregar(self) -> None:
        if not self.buf:
            return
        tab = pa.Table.from_pylist(self.buf, schema=SCHEMA_BRUTO)
        pq.write_table(tab, self.dir / f"part-{self.n_arq:05d}.parquet", compression="zstd")
        self.total += len(self.buf)
        self.n_arq += 1
        self.buf = []

    def fechar(self) -> int:
        self._descarregar()
        (self.dir / MARCADOR).write_text(str(self.total))
        return self.total


def extrair_dia(fonte: Fonte, dia: dt.date, dir_raw: Path, linhas_por_arquivo: int,
                lote: str, refazer: bool = False) -> int:
    destino = dir_raw / f"fonte={fonte.nome}" / f"dt={dia.isoformat()}"
    if (destino / MARCADOR).exists() and not refazer:
        log.debug("Partição já extraída: %s", destino)
        return -1
    if destino.exists():
        for p in destino.glob("*"):
            p.unlink()
    grav = GravadorParticao(destino, linhas_por_arquivo)
    for lote_linhas in fonte.ler_dia(dia):
        for chave, data_ref, bruto in lote_linhas:
            try:
                xml = decodificar(bruto, fonte.codificacao)
            except Exception as e:  # registra mesmo assim: vira erro de parse (regra R000)
                xml = f"<!-- ERRO_DECODIFICACAO: {e} -->".encode()
            grav.adicionar({
                "chave_origem": str(chave).strip() if chave is not None else None,
                "fonte": fonte.nome,
                "dt_ref": data_ref if isinstance(data_ref, dt.date) else dia,
                "xml": xml,
                "hash_xml": hashlib.sha256(xml).hexdigest(),
                "lote": lote,
            })
    return grav.fechar()


def extrair(fontes: list[Fonte], de: dt.date, ate: dt.date, dir_raw: Path, paralelismo: int,
            linhas_por_arquivo: int, lote: str, refazer: bool = False) -> dict:
    tarefas = [(f, d) for f in fontes for d in dias(de, ate)]
    resumo = {"particoes": 0, "puladas": 0, "xmls": 0, "falhas": []}
    with ThreadPoolExecutor(max_workers=max(1, paralelismo)) as ex:
        futs = {ex.submit(extrair_dia, f, d, dir_raw, linhas_por_arquivo, lote, refazer): (f.nome, d)
                for f, d in tarefas}
        for fut in as_completed(futs):
            nome, d = futs[fut]
            try:
                n = fut.result()
            except Exception as e:
                log.exception("Falha extraindo %s %s", nome, d)
                resumo["falhas"].append(f"{nome} {d}: {e}")
                continue
            if n < 0:
                resumo["puladas"] += 1
            else:
                resumo["particoes"] += 1
                resumo["xmls"] += n
                log.info("Extraído %s %s: %d XMLs", nome, d, n)
    return resumo
