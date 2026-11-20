from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg_teste(tmp_path):
    from auditoria_rt import config

    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    return config.carregar(None, {
        "workspace": {"diretorio": str(tmp_path / "workdir"), "duckdb_threads": 2, "duckdb_memoria": "1GB"},
        "extracao": {"fontes": [{"nome": "teste", "tipo": "arquivos", "diretorio": str(xml_dir)}]},
        "calculadora": {"modo": "tabela"},
        "amostra": {"tamanho": 50, "semente": 1},
        "referencias": {
            "classificacao_tributaria": str(RAIZ / "config/referencia/classificacao_tributaria.csv"),
            "aliquotas": str(RAIZ / "config/referencia/aliquotas_referencia.csv"),
            "matriz_expectativa": str(RAIZ / "config/referencia/matriz_expectativa.csv"),
        },
        "regras": {"padroes": {"min_itens_ncm": 1000}},
    })
