"""Leitura da configuração YAML com valores padrão e expansão de ${VARIAVEL}."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

PADRAO: dict[str, Any] = {
    "workspace": {"diretorio": "./workdir", "duckdb_threads": 4, "duckdb_memoria": "4GB"},
    "extracao": {"paralelismo": 1, "linhas_por_lote": 5000, "linhas_por_arquivo": 50000, "fontes": []},
    "calculadora": {
        "modo": "tabela",
        "url_base": "http://localhost:8080",
        "endpoint_calculo": "/api/calculadora/regime-geral",
        "endpoint_versao": None,
        "versao": None,
        "timeout_s": 60,
        "tentativas": 3,
        "workers": 8,
        "itens_por_requisicao": 100,
        "granularidade_data": "mes",
        "verificar_tls": True,
        "cabecalhos": {},
    },
    "amostra": {"tamanho": 2000, "semente": 42},
    "referencias": {
        "classificacao_tributaria": "./config/referencia/classificacao_tributaria.csv",
        "aliquotas": "./config/referencia/aliquotas_referencia.csv",
        "matriz_expectativa": "./config/referencia/matriz_expectativa.csv",
    },
    "regras": {
        "tolerancia_abs": 0.01,
        "tolerancia_rel": 0.0,
        "tolerancia_aliquota": 0.0001,
        "ibscbs_obrigatorio_desde": "2026-01-01",
        "base_calculo": {
            "v_prod": 1, "v_frete": 1, "v_seg": 1, "v_outro": 1, "v_desc": -1,
            "v_icms": -1, "v_pis": -1, "v_cofins": -1, "v_ipi": 0,
        },
        "padroes": {"min_itens_ncm": 50, "limiar_minoritario": 0.02},
        "desabilitadas": [],
        "severidade": {},
    },
    "relatorio": {"max_linhas_detalhe": 200000, "exportar_csv": True},
}

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expandir(valor: Any) -> Any:
    if isinstance(valor, str):
        def troca(m: re.Match) -> str:
            nome, padrao = m.group(1), m.group(2)
            if nome in os.environ:
                return os.environ[nome]
            if padrao is not None:
                return padrao
            raise KeyError(f"Variável de ambiente não definida: {nome}")

        return _VAR.sub(troca, valor)
    if isinstance(valor, dict):
        return {k: _expandir(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_expandir(v) for v in valor]
    return valor


def _mesclar(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _mesclar(out[k], v)
        else:
            out[k] = v
    return out


class Config(dict):
    """Dicionário de configuração com caminho de origem e hash (rastreabilidade)."""

    caminho: Path | None = None

    @property
    def hash(self) -> str:
        semsenha = _ocultar_segredos(self)
        bruto = json.dumps(semsenha, sort_keys=True, default=str).encode()
        return hashlib.sha256(bruto).hexdigest()[:16]

    def sem_segredos(self) -> dict:
        return _ocultar_segredos(self)


def _ocultar_segredos(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if any(s in k.lower() for s in ("senha", "password", "token", "authorization")) else _ocultar_segredos(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_ocultar_segredos(v) for v in obj]
    return obj


def carregar(caminho: str | Path | None = None, sobrescrever: dict | None = None, expandir_env: bool = True) -> Config:
    dados: dict = {}
    if caminho:
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}
    cfg = _mesclar(PADRAO, dados)
    cfg = _mesclar(cfg, sobrescrever or {})
    if expandir_env:
        # Fontes só são expandidas quando usadas (permite rodar regras sem credenciais do SAP).
        fontes = cfg["extracao"].pop("fontes", [])
        cfg = _expandir(cfg)
        cfg["extracao"]["fontes"] = fontes
    out = Config(cfg)
    out.caminho = Path(caminho) if caminho else None
    return out


def expandir(valor: Any) -> Any:
    """Expande variáveis de ambiente sob demanda (usado nas fontes de extração)."""
    return _expandir(valor)
