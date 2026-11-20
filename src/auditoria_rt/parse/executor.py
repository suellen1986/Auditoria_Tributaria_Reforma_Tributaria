"""Processa os parquets brutos em paralelo (um processo por arquivo).

Saída espelha a estrutura do bruto:
  parsed/{notas,itens,erros}/fonte=<f>/dt=<d>/part-NNNNN.parquet
Arquivos já processados são pulados (retomada após falha).
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from auditoria_rt.parse.esquema import SCHEMA_ERRO, SCHEMA_ITEM, SCHEMA_NOTA
from auditoria_rt.parse.nfe import parse_nfe

log = logging.getLogger(__name__)


def _destinos(arq: Path, dir_raw: Path, dir_parsed: Path) -> dict[str, Path]:
    rel = arq.relative_to(dir_raw)
    return {t: dir_parsed / t / rel for t in ("notas", "itens", "erros")}


def processar_arquivo(arq: str, dir_raw: str, dir_parsed: str) -> tuple[int, int, int]:
    arq_p, raw_p, parsed_p = Path(arq), Path(dir_raw), Path(dir_parsed)
    dest = _destinos(arq_p, raw_p, parsed_p)
    notas, itens, erros = [], [], []
    pf = pq.ParquetFile(arq_p)
    for lote in pf.iter_batches(batch_size=2000):
        for r in lote.to_pylist():
            try:
                nota, its = parse_nfe(r["xml"], r["chave_origem"], r["fonte"], r["hash_xml"], r["lote"])
                if not its:
                    raise ValueError("NF-e sem itens (det)")
                notas.append(nota)
                itens.extend(its)
            except Exception as e:
                erros.append({
                    "chave_origem": r["chave_origem"], "fonte": r["fonte"], "dt_ref": r["dt_ref"],
                    "erro": f"{type(e).__name__}: {e}"[:1000], "hash_xml": r["hash_xml"], "lote": r["lote"],
                })
    for tipo, linhas, sch in (("notas", notas, SCHEMA_NOTA), ("itens", itens, SCHEMA_ITEM), ("erros", erros, SCHEMA_ERRO)):
        dest[tipo].parent.mkdir(parents=True, exist_ok=True)
        tmp = dest[tipo].with_suffix(".tmp")
        pq.write_table(pa.Table.from_pylist(linhas, schema=sch), tmp, compression="zstd")
        os.replace(tmp, dest[tipo])
    return len(notas), len(itens), len(erros)


def processar(dir_raw: Path, dir_parsed: Path, workers: int | None = None, refazer: bool = False) -> dict:
    arquivos = sorted(dir_raw.rglob("*.parquet"))
    pendentes = []
    for a in arquivos:
        d = _destinos(a, dir_raw, dir_parsed)
        # "erros" é o último gravado: se existe, o arquivo foi concluído
        if refazer or not d["erros"].exists() or d["erros"].stat().st_mtime < a.stat().st_mtime:
            pendentes.append(a)
    resumo = {"arquivos": len(arquivos), "processados": 0, "notas": 0, "itens": 0, "erros": 0}
    if not pendentes:
        return resumo
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    log.info("Processando %d de %d arquivos com %d processos", len(pendentes), len(arquivos), workers)
    if workers == 1:
        resultados = (processar_arquivo(str(a), str(dir_raw), str(dir_parsed)) for a in pendentes)
        for n, i, e in resultados:
            resumo["processados"] += 1
            resumo["notas"] += n
            resumo["itens"] += i
            resumo["erros"] += e
        return resumo
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(processar_arquivo, str(a), str(dir_raw), str(dir_parsed)): a for a in pendentes}
        for k, fut in enumerate(as_completed(futs), 1):
            n, i, e = fut.result()
            resumo["processados"] += 1
            resumo["notas"] += n
            resumo["itens"] += i
            resumo["erros"] += e
            if k % 50 == 0 or k == len(pendentes):
                log.info("Parse: %d/%d arquivos (%d notas, %d itens, %d erros)",
                         k, len(pendentes), resumo["notas"], resumo["itens"], resumo["erros"])
    return resumo
