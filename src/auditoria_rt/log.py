from __future__ import annotations

import logging
import sys
from pathlib import Path


def configurar(diretorio: Path | None = None, nivel: int = logging.INFO) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    raiz.addHandler(console)
    if diretorio:
        diretorio.mkdir(parents=True, exist_ok=True)
        arq = logging.FileHandler(diretorio / "auditoria.log", encoding="utf-8")
        arq.setFormatter(fmt)
        raiz.addHandler(arq)
