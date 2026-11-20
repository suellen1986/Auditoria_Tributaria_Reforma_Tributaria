"""Esquemas (pyarrow) das tabelas normalizadas. Ver docs/dicionario_dados.md."""

from __future__ import annotations

import pyarrow as pa

S, F, I, B, D = pa.string(), pa.float64(), pa.int32(), pa.bool_(), pa.date32()

CAMPOS_BRUTO = [
    ("chave_origem", S), ("fonte", S), ("dt_ref", D), ("xml", pa.binary()), ("hash_xml", S), ("lote", S),
]

CAMPOS_NOTA = [
    ("chave", S), ("fonte", S), ("versao_leiaute", S), ("mod", S), ("serie", S), ("n_nf", S),
    ("tp_nf", S), ("fin_nfe", S), ("dh_emi", S), ("dt_emi", D),
    ("cnpj_emit", S), ("x_nome_emit", S), ("uf_emit", S),
    ("cnpj_dest", S), ("x_nome_dest", S), ("uf_dest", S),
    ("qtd_itens", I), ("v_nf", F),
    ("tot_presente", B), ("tot_v_bc_ibscbs", F), ("tot_v_ibs_uf", F), ("tot_v_ibs_mun", F),
    ("tot_v_ibs", F), ("tot_v_cbs", F), ("tot_v_ibs_mono", F), ("tot_v_cbs_mono", F), ("tot_v_is", F),
    ("hash_xml", S), ("lote", S),
]

_GRUPO = ["p_{g}", "p_dif_{g}", "v_dif_{g}", "v_dev_trib_{g}", "p_red_aliq_{g}", "p_aliq_efet_{g}", "v_{g}"]


def _grupo(sufixo: str, nome_valor: str) -> list[tuple[str, pa.DataType]]:
    campos = []
    for modelo in _GRUPO:
        nome = modelo.format(g=sufixo)
        if modelo == "p_{g}":
            nome = f"p_{nome_valor}"
        elif modelo == "v_{g}":
            nome = f"v_{nome_valor}"
        campos.append((nome, F))
    return campos


CAMPOS_MONO = [
    "q_bc_mono", "ad_rem_ibs", "ad_rem_cbs", "v_ibs_mono", "v_cbs_mono",
    "q_bc_mono_reten", "ad_rem_ibs_reten", "v_ibs_mono_reten", "ad_rem_cbs_reten", "v_cbs_mono_reten",
    "q_bc_mono_ret", "ad_rem_ibs_ret", "v_ibs_mono_ret", "ad_rem_cbs_ret", "v_cbs_mono_ret",
]

CAMPOS_ITEM = (
    [
        ("chave", S), ("n_item", I), ("fonte", S), ("dt_emi", D), ("mod", S), ("tp_nf", S), ("fin_nfe", S),
        ("cnpj_emit", S), ("uf_emit", S), ("c_mun_emit", S),
        ("cnpj_dest", S), ("uf_dest", S), ("c_mun_dest", S),
        ("uf_entrega", S), ("c_mun_entrega", S), ("c_mun_fg", S), ("c_mun_fg_ibs", S),
        ("c_prod", S), ("x_prod", S), ("ncm", S), ("cest", S), ("cfop", S),
        ("u_com", S), ("q_com", F), ("u_trib", S), ("q_trib", F),
        ("v_prod", F), ("v_frete", F), ("v_seg", F), ("v_desc", F), ("v_outro", F),
        ("v_icms", F), ("v_icms_st", F), ("v_ipi", F), ("v_pis", F), ("v_cofins", F),
        ("ibscbs_presente", B), ("cst", S), ("cclasstrib", S), ("v_bc", F),
    ]
    + _grupo("uf", "ibs_uf")       # p_ibs_uf, p_dif_uf, v_dif_uf, v_dev_trib_uf, p_red_aliq_uf, p_aliq_efet_uf, v_ibs_uf
    + _grupo("mun", "ibs_mun")
    + [("v_ibs", F)]
    + _grupo("cbs", "cbs")         # p_cbs, p_dif_cbs, ..., v_cbs
    + [
        ("tem_g_red", B), ("tem_g_dif", B), ("tem_g_dev_trib", B), ("tem_g_trib_regular", B),
        ("tem_g_cred_pres", B), ("tem_g_trib_compra_gov", B), ("tem_mono", B),
    ]
    + [(c, F) for c in CAMPOS_MONO]
    + [
        ("is_presente", B), ("cst_is", S), ("cclasstrib_is", S), ("v_bc_is", F), ("p_is", F),
        ("p_is_espec", F), ("u_trib_is", S), ("q_trib_is", F), ("v_is", F),
        ("hash_xml", S), ("lote", S),
    ]
)

CAMPOS_ERRO = [("chave_origem", S), ("fonte", S), ("dt_ref", D), ("erro", S), ("hash_xml", S), ("lote", S)]


def schema(campos) -> pa.Schema:
    return pa.schema([pa.field(n, t) for n, t in campos])


SCHEMA_BRUTO = schema(CAMPOS_BRUTO)
SCHEMA_NOTA = schema(CAMPOS_NOTA)
SCHEMA_ITEM = schema(CAMPOS_ITEM)
SCHEMA_ERRO = schema(CAMPOS_ERRO)
