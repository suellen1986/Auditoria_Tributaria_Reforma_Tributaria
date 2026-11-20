"""Bloco B - Aderência à regra: comparação com a calculadora (via cache de alíquotas)."""

from auditoria_rt.rules.base import Regra

_ESPERADO = "round(v_bc * {aliq} / 100, 2) - coalesce({dif}, 0) - coalesce({dev}, 0)"


def _regra_valor(id_, tributo, campo, valor, aliq, dif, dev):
    esperado = _ESPERADO.format(aliq=aliq, dif=dif, dev=dev)
    return Regra(
        id=id_, titulo=f"{campo} diferente do recalculado pela calculadora", bloco="CALCULO", severidade="ALTA",
        financeira=True,
        descricao=f"Valor de {tributo} declarado diferente de vBC x alíquota efetiva devolvida pela calculadora "
                  f"(deduzidos diferimento e devolução declarados).",
        fundamento="Calculadora oficial de IBS/CBS (RFB/CGIBS); LC 214/2025.",
        sql=f"""
            SELECT * FROM (
              SELECT chave, n_item, '{campo}' AS campo, {valor} AS valor_declarado, {esperado} AS valor_esperado,
                     'Calculadora: ' || round({aliq}, 6) || '% (CST ' || cst || '/' || coalesce(cclasstrib, '-') || ')' AS detalhe
              FROM itens_calc
              WHERE calc_status = 'OK' AND v_bc IS NOT NULL AND {aliq} IS NOT NULL AND NOT coalesce(tem_mono, false)
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    )


REGRAS = [
    _regra_valor("C001", "CBS", "vCBS", "v_cbs", "calc_aliq_cbs", "v_dif_cbs", "v_dev_trib_cbs"),
    _regra_valor("C002", "IBS estadual", "vIBSUF", "v_ibs_uf", "calc_aliq_ibs_uf", "v_dif_uf", "v_dev_trib_uf"),
    _regra_valor("C003", "IBS municipal", "vIBSMun", "v_ibs_mun", "calc_aliq_ibs_mun", "v_dif_mun", "v_dev_trib_mun"),
    Regra(
        id="C004", titulo="Alíquota efetiva diferente da calculadora", bloco="CALCULO", severidade="MEDIA",
        descricao="Alíquota efetiva declarada (pAliqEfet ou alíquota nominal) diferente da devolvida pela calculadora "
                  "para a mesma data, local, NCM e classificação.",
        fundamento="Calculadora oficial de IBS/CBS.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'aliq. efetiva CBS' AS campo, coalesce(p_aliq_efet_cbs, p_cbs) AS valor_declarado,
                     calc_aliq_cbs AS valor_esperado, 'CST ' || cst || '/' || coalesce(cclasstrib, '-') AS detalhe
              FROM itens_calc WHERE calc_status = 'OK' AND coalesce(p_aliq_efet_cbs, p_cbs) IS NOT NULL AND calc_aliq_cbs IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'aliq. efetiva IBS UF', coalesce(p_aliq_efet_uf, p_ibs_uf), calc_aliq_ibs_uf,
                     'CST ' || cst || '/' || coalesce(cclasstrib, '-')
              FROM itens_calc WHERE calc_status = 'OK' AND coalesce(p_aliq_efet_uf, p_ibs_uf) IS NOT NULL AND calc_aliq_ibs_uf IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'aliq. efetiva IBS Mun', coalesce(p_aliq_efet_mun, p_ibs_mun), calc_aliq_ibs_mun,
                     'CST ' || cst || '/' || coalesce(cclasstrib, '-')
              FROM itens_calc WHERE calc_status = 'OK' AND coalesce(p_aliq_efet_mun, p_ibs_mun) IS NOT NULL AND calc_aliq_ibs_mun IS NOT NULL
            ) WHERE fora_tol_aliq(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="C005", titulo="Combinação rejeitada pela calculadora", bloco="CALCULO", severidade="ALTA",
        descricao="A calculadora recusou a combinação de data, local, NCM, CST e cClassTrib do item (ex.: classificação não aplicável ao NCM).",
        fundamento="Calculadora oficial de IBS/CBS.",
        sql="""
            SELECT chave, n_item, 'CST/cClassTrib' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   coalesce(calc_mensagem, 'Rejeitado') AS detalhe
            FROM itens_calc WHERE calc_status = 'ERRO'
        """,
    ),
    Regra(
        id="C006", titulo="Item não recalculado", bloco="CALCULO", severidade="INFO",
        descricao="O item não tem resultado da calculadora (indisponibilidade ou etapa de cálculo não executada). "
                  "Não é desvio fiscal: indica cobertura incompleta da auditoria.",
        fundamento="Cobertura da auditoria.",
        sql="""
            SELECT chave, n_item, 'calculadora' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'Sem resultado da calculadora versão $versao' AS detalhe
            FROM itens_calc WHERE calc_status IS NULL AND cst IS NOT NULL
        """,
    ),
    Regra(
        id="C007", titulo="Amostra: cálculo completo diverge do atalho por alíquota", bloco="CALCULO", severidade="MEDIA",
        descricao="Validação metodológica: na amostra, o valor calculado item a item pela calculadora difere do valor obtido "
                  "aplicando a alíquota em cache. Indica que a alíquota depende de outro parâmetro (revisar chave do cache).",
        fundamento="Controle de qualidade da metodologia (premissa P-01).",
        sql="""
            SELECT * FROM (
              SELECT i.chave, i.n_item, 'amostra vCBS' AS campo, a.v_cbs AS valor_declarado,
                     round(i.v_bc * i.calc_aliq_cbs / 100, 2) AS valor_esperado,
                     'declarado = cálculo completo; esperado = atalho' AS detalhe
              FROM calc_amostra a JOIN itens_calc i ON i.chave = a.chave AND i.n_item = a.n_item
              WHERE a.execucao = '$execucao' AND a.status = 'OK' AND i.calc_status = 'OK' AND a.v_cbs IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'amostra vIBSUF', a.v_ibs_uf, round(i.v_bc * i.calc_aliq_ibs_uf / 100, 2),
                     'declarado = cálculo completo; esperado = atalho'
              FROM calc_amostra a JOIN itens_calc i ON i.chave = a.chave AND i.n_item = a.n_item
              WHERE a.execucao = '$execucao' AND a.status = 'OK' AND i.calc_status = 'OK' AND a.v_ibs_uf IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'amostra vIBSMun', a.v_ibs_mun, round(i.v_bc * i.calc_aliq_ibs_mun / 100, 2),
                     'declarado = cálculo completo; esperado = atalho'
              FROM calc_amostra a JOIN itens_calc i ON i.chave = a.chave AND i.n_item = a.n_item
              WHERE a.execucao = '$execucao' AND a.status = 'OK' AND i.calc_status = 'OK' AND a.v_ibs_mun IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="C008", titulo="Monofásico: valor diferente do ad rem da calculadora", bloco="CALCULO", severidade="ALTA",
        financeira=True,
        descricao="vIBSMono/vCBSMono diferente de quantidade x alíquota ad rem devolvida pela calculadora.",
        fundamento="LC 214/2025 - combustíveis; calculadora oficial.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIBSMono' AS campo, v_ibs_mono AS valor_declarado,
                     round(q_bc_mono * calc_ad_rem_ibs, 2) AS valor_esperado,
                     'Ad rem calculadora ' || calc_ad_rem_ibs || ' x ' || q_bc_mono AS detalhe
              FROM itens_calc WHERE calc_status = 'OK' AND tem_mono AND q_bc_mono IS NOT NULL AND calc_ad_rem_ibs IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vCBSMono', v_cbs_mono, round(q_bc_mono * calc_ad_rem_cbs, 2),
                     'Ad rem calculadora ' || calc_ad_rem_cbs || ' x ' || q_bc_mono
              FROM itens_calc WHERE calc_status = 'OK' AND tem_mono AND q_bc_mono IS NOT NULL AND calc_ad_rem_cbs IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
]
