"""Gera massa sintética direto no formato bruto (workdir/raw) para teste de carga.

Uso:
  python scripts/gerar_massa_sintetica.py --workdir ./workdir_carga --notas 1000000 --de 2026-03-01 --ate 2026-03-31
  auditoria-rt -c config/config.carga.yaml executar --de 2026-03-01 --ate 2026-03-31 --sem-extracao
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
from pathlib import Path

from auditoria_rt.extract.base import GravadorParticao
from auditoria_rt.sintetico import gerar_xml, nota_aleatoria


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--notas", type=int, default=100000)
    ap.add_argument("--de", type=dt.date.fromisoformat, default=dt.date(2026, 3, 1))
    ap.add_argument("--ate", type=dt.date.fromisoformat, default=dt.date(2026, 3, 31))
    ap.add_argument("--semente", type=int, default=1)
    a = ap.parse_args()

    rnd = random.Random(a.semente)
    n_dias = (a.ate - a.de).days + 1
    por_dia = max(1, a.notas // n_dias)
    k = 0
    for d in range(n_dias):
        dia = a.de + dt.timedelta(days=d)
        grav = GravadorParticao(Path(a.workdir) / "raw" / "fonte=sintetico" / f"dt={dia.isoformat()}", 50000)
        for _ in range(por_dia):
            k += 1
            nota = nota_aleatoria(k, dia, rnd)
            xml = gerar_xml(nota).encode()
            grav.adicionar({"chave_origem": nota.chave, "fonte": "sintetico", "dt_ref": dia, "xml": xml,
                            "hash_xml": hashlib.sha256(xml).hexdigest(), "lote": "carga"})
        grav.fechar()
        print(f"{dia}: {por_dia} notas")
    print(f"Total: {k} notas em {a.workdir}/raw")


if __name__ == "__main__":
    main()
