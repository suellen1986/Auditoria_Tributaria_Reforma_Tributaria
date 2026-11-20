from __future__ import annotations

from auditoria_rt.config import expandir
from auditoria_rt.extract.base import Fonte


def criar_fonte(cfg_fonte: dict, cfg_extracao: dict) -> Fonte:
    cfg_fonte = expandir(cfg_fonte)
    tipo = cfg_fonte.get("tipo", "hana")
    if tipo == "hana":
        from auditoria_rt.extract.sql import FonteHana
        return FonteHana(cfg_fonte, cfg_extracao)
    if tipo == "odbc":
        from auditoria_rt.extract.sql import FonteODBC
        return FonteODBC(cfg_fonte, cfg_extracao)
    if tipo == "arquivos":
        from auditoria_rt.extract.arquivos import FonteArquivos
        return FonteArquivos(cfg_fonte, cfg_extracao)
    raise ValueError(f"Tipo de fonte desconhecido: {tipo}")
