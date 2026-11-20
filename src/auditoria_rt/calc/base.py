from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Base e quantidade de referência para obter alíquotas efetivas com precisão
# (valor / BASE_REF * 100 = alíquota em %, com 6 casas).
BASE_REF = 1_000_000.0
QTD_REF = 1_000_000.0


@dataclass(frozen=True)
class ParametroCalculo:
    data: dt.date
    uf: str
    c_mun: str
    ncm: str
    cst: str
    cclasstrib: str
    u_trib: str = ""
    base: float = BASE_REF
    quantidade: float = QTD_REF
    ref: Any = None  # identificador devolvido no resultado (chave do cache ou (chave, n_item))


@dataclass
class ResultadoCalculo:
    ref: Any
    status: str = "OK"            # OK | ERRO
    mensagem: str | None = None
    p_ibs_uf: float | None = None
    p_ibs_mun: float | None = None
    p_cbs: float | None = None
    v_ibs_uf: float | None = None
    v_ibs_mun: float | None = None
    v_cbs: float | None = None
    v_ibs_mono: float | None = None
    v_cbs_mono: float | None = None
    resposta: str | None = None
    extras: dict = field(default_factory=dict)


class Calculadora(ABC):
    versao: str = "desconhecida"

    @abstractmethod
    def calcular(self, params: list[ParametroCalculo]) -> list[ResultadoCalculo]:
        """Calcula um grupo de parâmetros (mesma data/UF/município)."""

    def testar(self) -> str:
        return "ok"
