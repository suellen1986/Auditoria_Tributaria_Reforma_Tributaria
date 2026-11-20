"""Fonte por arquivos: diretório com .xml e/ou .zip (exportações, testes de bancada)."""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from pathlib import Path
from typing import Iterator

from auditoria_rt.extract.base import Fonte

_DH = re.compile(rb"<(?:\w+:)?dhEmi>(\d{4}-\d{2}-\d{2})")
_ID = re.compile(rb'Id="NFe(\d{44})"')


class FonteArquivos(Fonte):
    def __init__(self, cfg_fonte: dict, cfg_extracao: dict):
        super().__init__(cfg_fonte, cfg_extracao)
        self.dir = Path(cfg_fonte["diretorio"])
        self._indice: dict[dt.date, list[tuple[str, bytes]]] | None = None

    def _conteudos(self) -> Iterator[tuple[str, bytes]]:
        for p in sorted(self.dir.rglob("*")):
            if p.suffix.lower() == ".xml":
                yield p.name, p.read_bytes()
            elif p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        if n.lower().endswith(".xml"):
                            yield n, z.read(n)

    def _indexar(self) -> dict:
        if self._indice is None:
            idx: dict = {}
            for nome, conteudo in self._conteudos():
                m = _DH.search(conteudo)
                d = dt.date.fromisoformat(m.group(1).decode()) if m else dt.date(1900, 1, 1)
                mid = _ID.search(conteudo)
                chave = mid.group(1).decode() if mid else nome
                idx.setdefault(d, []).append((chave, conteudo))
            self._indice = idx
        return self._indice

    def ler_dia(self, dia: dt.date) -> Iterator[list[tuple]]:
        regs = self._indexar().get(dia, [])
        for i in range(0, len(regs), self.linhas_por_lote):
            yield [(ch, dia, xml) for ch, xml in regs[i:i + self.linhas_por_lote]]

    def datas(self) -> list[dt.date]:
        return sorted(self._indexar())

    def testar(self) -> str:
        n = sum(len(v) for v in self._indexar().values())
        return f"{n} XMLs encontrados em {self.dir}"
