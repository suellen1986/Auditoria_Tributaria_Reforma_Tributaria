"""Bloco A - Estrutura e consistência interna (não depende da calculadora)."""

from auditoria_rt.rules.base import Regra

REGRAS = [
    Regra(
        id="R000", titulo="XML inválido ou não processável", bloco="ESTRUTURA", severidade="ALTA",
        descricao="O XML extraído do SAP não pôde ser lido (malformado, sem infNFe, sem itens ou codificação desconhecida).",
        fundamento="Integridade da base auditada.",
        sql="""
            SELECT coalesce(chave_origem, hash_xml) AS chave, NULL AS n_item, 'XML' AS campo,
                   NULL AS valor_declarado, NULL AS valor_esperado, erro AS detalhe
            FROM erros
        """,
    ),
    Regra(
        id="R001", titulo="Grupo IBSCBS ausente no item", bloco="ESTRUTURA", severidade="ALTA",
        descricao="Item emitido a partir da data de obrigatoriedade configurada sem o grupo IBSCBS.",
        fundamento="NT 2025.002 - grupo UB (IBSCBS) do item; LC 214/2025.",
        sql="""
            SELECT chave, n_item, 'IBSCBS' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'Item sem grupo IBSCBS (emissão ' || dt_emi || ', CFOP ' || coalesce(cfop, '-') || ')' AS detalhe
            FROM itens
            WHERE NOT coalesce(ibscbs_presente, false) AND dt_emi >= DATE '$obrig_desde'
        """,
    ),
    Regra(
        id="R002", titulo="CST de IBS/CBS inexistente", bloco="ESTRUTURA", severidade="ALTA",
        descricao="CST informado não consta na tabela oficial de classificação tributária.",
        fundamento="Tabela de CST/cClassTrib (anexo da NT 2025.002).",
        sql="""
            SELECT i.chave, i.n_item, 'CST' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'CST ' || coalesce(i.cst, '(vazio)') || ' não consta na tabela de classificação' AS detalhe
            FROM itens i
            WHERE i.ibscbs_presente
              AND NOT EXISTS (SELECT 1 FROM ref_class_trib r WHERE r.cst = i.cst)
        """,
    ),
    Regra(
        id="R003", titulo="cClassTrib inexistente ou incompatível com o CST", bloco="ESTRUTURA", severidade="ALTA",
        descricao="O código de classificação tributária não existe ou não pertence ao CST informado.",
        fundamento="Tabela de CST/cClassTrib (anexo da NT 2025.002).",
        sql="""
            SELECT i.chave, i.n_item, 'cClassTrib' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'cClassTrib ' || coalesce(i.cclasstrib, '(vazio)') || ' não existe para o CST ' || i.cst AS detalhe
            FROM itens i
            WHERE i.ibscbs_presente
              AND EXISTS (SELECT 1 FROM ref_class_trib r WHERE r.cst = i.cst)
              AND NOT EXISTS (SELECT 1 FROM ref_class_trib r WHERE r.cst = i.cst AND r.cclasstrib = i.cclasstrib)
        """,
    ),
    Regra(
        id="R004", titulo="cClassTrib fora da vigência", bloco="ESTRUTURA", severidade="ALTA",
        descricao="A classificação existe, mas não estava vigente na data de emissão.",
        fundamento="Vigência da tabela de cClassTrib.",
        sql="""
            SELECT i.chave, i.n_item, 'cClassTrib' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'cClassTrib ' || i.cclasstrib || ' não vigente em ' || i.dt_emi AS detalhe
            FROM itens i
            WHERE i.ibscbs_presente
              AND EXISTS (SELECT 1 FROM ref_class_trib r WHERE r.cst = i.cst AND r.cclasstrib = i.cclasstrib)
              AND NOT EXISTS (
                SELECT 1 FROM ref_class_trib r
                WHERE r.cst = i.cst AND r.cclasstrib = i.cclasstrib
                  AND i.dt_emi BETWEEN coalesce(r.ini_vigencia, DATE '1900-01-01')
                                   AND coalesce(r.fim_vigencia, DATE '9999-12-31'))
        """,
    ),
    Regra(
        id="R005", titulo="Grupo exigido pela classificação ausente", bloco="ESTRUTURA", severidade="ALTA",
        descricao="A classificação exige um grupo (redução, diferimento, monofásico, tributação regular, crédito presumido) que não foi informado.",
        fundamento="Indicadores de grupos da tabela de cClassTrib.",
        sql="""
            SELECT chave, n_item, 'grupos' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'cClassTrib ' || cclasstrib || ' exige: ' || faltando AS detalhe
            FROM (
              SELECT i.chave, i.n_item, i.cclasstrib, concat_ws(', ',
                  CASE WHEN r.g_red = 'OBRIGATORIO' AND NOT coalesce(i.tem_g_red, false) THEN 'gRed' END,
                  CASE WHEN r.g_dif = 'OBRIGATORIO' AND NOT coalesce(i.tem_g_dif, false) THEN 'gDif' END,
                  CASE WHEN r.g_mono = 'OBRIGATORIO' AND NOT coalesce(i.tem_mono, false) THEN 'gIBSCBSMono' END,
                  CASE WHEN r.g_trib_regular = 'OBRIGATORIO' AND NOT coalesce(i.tem_g_trib_regular, false) THEN 'gTribRegular' END,
                  CASE WHEN r.g_cred_pres = 'OBRIGATORIO' AND NOT coalesce(i.tem_g_cred_pres, false) THEN 'gCredPres' END
              ) AS faltando
              FROM itens i JOIN ref_ct r ON r.cst = i.cst AND r.cclasstrib = i.cclasstrib
              WHERE i.ibscbs_presente
            ) WHERE faltando <> ''
        """,
    ),
    Regra(
        id="R006", titulo="Grupo não permitido pela classificação", bloco="ESTRUTURA", severidade="MEDIA",
        descricao="O item traz um grupo que a classificação tributária não admite (ex.: redução em operação de tributação integral).",
        fundamento="Indicadores de grupos da tabela de cClassTrib.",
        sql="""
            SELECT chave, n_item, 'grupos' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'cClassTrib ' || cclasstrib || ' não admite: ' || indevidos AS detalhe
            FROM (
              SELECT i.chave, i.n_item, i.cclasstrib, concat_ws(', ',
                  CASE WHEN r.g_red = 'PROIBIDO' AND coalesce(i.tem_g_red, false) THEN 'gRed' END,
                  CASE WHEN r.g_dif = 'PROIBIDO' AND coalesce(i.tem_g_dif, false) THEN 'gDif' END,
                  CASE WHEN r.g_mono = 'PROIBIDO' AND coalesce(i.tem_mono, false) THEN 'gIBSCBSMono' END,
                  CASE WHEN r.g_trib_regular = 'PROIBIDO' AND coalesce(i.tem_g_trib_regular, false) THEN 'gTribRegular' END,
                  CASE WHEN r.g_cred_pres = 'PROIBIDO' AND coalesce(i.tem_g_cred_pres, false) THEN 'gCredPres' END
              ) AS indevidos
              FROM itens i JOIN ref_ct r ON r.cst = i.cst AND r.cclasstrib = i.cclasstrib
              WHERE i.ibscbs_presente
            ) WHERE indevidos <> ''
        """,
    ),
    Regra(
        id="R007", titulo="Alíquota efetiva inconsistente com o percentual de redução", bloco="ESTRUTURA",
        severidade="ALTA",
        descricao="pAliqEfet diferente de alíquota x (1 - pRedAliq/100) no grupo de redução.",
        fundamento="NT 2025.002 - grupo gRed.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'pAliqEfet IBS UF' AS campo, p_aliq_efet_uf AS valor_declarado,
                     p_ibs_uf * (1 - coalesce(p_red_aliq_uf, 0) / 100) AS valor_esperado,
                     'pIBSUF ' || p_ibs_uf || ' com redução de ' || coalesce(p_red_aliq_uf, 0) || '%' AS detalhe
              FROM itens WHERE tem_g_red AND p_aliq_efet_uf IS NOT NULL AND p_ibs_uf IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'pAliqEfet IBS Mun', p_aliq_efet_mun, p_ibs_mun * (1 - coalesce(p_red_aliq_mun, 0) / 100),
                     'pIBSMun ' || p_ibs_mun || ' com redução de ' || coalesce(p_red_aliq_mun, 0) || '%'
              FROM itens WHERE tem_g_red AND p_aliq_efet_mun IS NOT NULL AND p_ibs_mun IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'pAliqEfet CBS', p_aliq_efet_cbs, p_cbs * (1 - coalesce(p_red_aliq_cbs, 0) / 100),
                     'pCBS ' || p_cbs || ' com redução de ' || coalesce(p_red_aliq_cbs, 0) || '%'
              FROM itens WHERE tem_g_red AND p_aliq_efet_cbs IS NOT NULL AND p_cbs IS NOT NULL
            ) WHERE fora_tol_aliq(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R008", titulo="Percentual de redução diferente do previsto na classificação", bloco="ESTRUTURA",
        severidade="ALTA",
        descricao="pRedAliq informado difere do percentual de redução da tabela de cClassTrib.",
        fundamento="Tabela de cClassTrib (pRedIBS/pRedCBS); LC 214/2025 - reduções.",
        sql="""
            SELECT * FROM (
              SELECT i.chave, i.n_item, 'pRedAliq IBS UF' AS campo, i.p_red_aliq_uf AS valor_declarado,
                     r.p_red_ibs AS valor_esperado, 'cClassTrib ' || i.cclasstrib AS detalhe
              FROM itens i JOIN ref_ct r ON r.cst = i.cst AND r.cclasstrib = i.cclasstrib
              WHERE i.tem_g_red AND i.p_red_aliq_uf IS NOT NULL AND r.p_red_ibs IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'pRedAliq IBS Mun', i.p_red_aliq_mun, r.p_red_ibs, 'cClassTrib ' || i.cclasstrib
              FROM itens i JOIN ref_ct r ON r.cst = i.cst AND r.cclasstrib = i.cclasstrib
              WHERE i.tem_g_red AND i.p_red_aliq_mun IS NOT NULL AND r.p_red_ibs IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'pRedAliq CBS', i.p_red_aliq_cbs, r.p_red_cbs, 'cClassTrib ' || i.cclasstrib
              FROM itens i JOIN ref_ct r ON r.cst = i.cst AND r.cclasstrib = i.cclasstrib
              WHERE i.tem_g_red AND i.p_red_aliq_cbs IS NOT NULL AND r.p_red_cbs IS NOT NULL
            ) WHERE fora_tol_aliq(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R009", titulo="vIBSUF diferente de vBC x alíquota", bloco="ESTRUTURA", severidade="ALTA", financeira=True,
        descricao="Valor do IBS estadual não confere com base x alíquota (efetiva, se houver redução), deduzidos diferimento e devolução.",
        fundamento="NT 2025.002 - regras de cálculo do grupo gIBSUF.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIBSUF' AS campo, v_ibs_uf AS valor_declarado,
                     round(v_bc * coalesce(p_aliq_efet_uf, p_ibs_uf) / 100, 2)
                       - coalesce(v_dif_uf, 0) - coalesce(v_dev_trib_uf, 0) AS valor_esperado,
                     'vBC ' || v_bc || ' x ' || coalesce(p_aliq_efet_uf, p_ibs_uf) || '%' AS detalhe
              FROM itens
              WHERE ibscbs_presente AND v_bc IS NOT NULL AND coalesce(p_aliq_efet_uf, p_ibs_uf) IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R010", titulo="vIBSMun diferente de vBC x alíquota", bloco="ESTRUTURA", severidade="ALTA", financeira=True,
        descricao="Valor do IBS municipal não confere com base x alíquota, deduzidos diferimento e devolução.",
        fundamento="NT 2025.002 - regras de cálculo do grupo gIBSMun.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIBSMun' AS campo, v_ibs_mun AS valor_declarado,
                     round(v_bc * coalesce(p_aliq_efet_mun, p_ibs_mun) / 100, 2)
                       - coalesce(v_dif_mun, 0) - coalesce(v_dev_trib_mun, 0) AS valor_esperado,
                     'vBC ' || v_bc || ' x ' || coalesce(p_aliq_efet_mun, p_ibs_mun) || '%' AS detalhe
              FROM itens
              WHERE ibscbs_presente AND v_bc IS NOT NULL AND coalesce(p_aliq_efet_mun, p_ibs_mun) IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R011", titulo="vCBS diferente de vBC x alíquota", bloco="ESTRUTURA", severidade="ALTA", financeira=True,
        descricao="Valor da CBS não confere com base x alíquota, deduzidos diferimento e devolução.",
        fundamento="NT 2025.002 - regras de cálculo do grupo gCBS.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vCBS' AS campo, v_cbs AS valor_declarado,
                     round(v_bc * coalesce(p_aliq_efet_cbs, p_cbs) / 100, 2)
                       - coalesce(v_dif_cbs, 0) - coalesce(v_dev_trib_cbs, 0) AS valor_esperado,
                     'vBC ' || v_bc || ' x ' || coalesce(p_aliq_efet_cbs, p_cbs) || '%' AS detalhe
              FROM itens
              WHERE ibscbs_presente AND v_bc IS NOT NULL AND coalesce(p_aliq_efet_cbs, p_cbs) IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R012", titulo="vIBS diferente de vIBSUF + vIBSMun", bloco="ESTRUTURA", severidade="ALTA", financeira=True,
        descricao="O total de IBS do item não é a soma das parcelas estadual e municipal.",
        fundamento="NT 2025.002 - campo vIBS.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIBS' AS campo, v_ibs AS valor_declarado,
                     coalesce(v_ibs_uf, 0) + coalesce(v_ibs_mun, 0) AS valor_esperado,
                     'vIBSUF ' || coalesce(v_ibs_uf, 0) || ' + vIBSMun ' || coalesce(v_ibs_mun, 0) AS detalhe
              FROM itens WHERE ibscbs_presente AND v_ibs IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R013", titulo="Totais IBSCBSTot diferentes da soma dos itens", bloco="ESTRUTURA", severidade="ALTA",
        financeira=True,
        descricao="Totalizadores da nota (vBCIBSCBS, vIBSUF, vIBSMun, vIBS, vCBS, monofásico) não conferem com a soma dos itens.",
        fundamento="NT 2025.002 - grupo W03 (IBSCBSTot).",
        sql="""
            WITH s AS (
              SELECT chave, sum(v_bc) AS vbc, sum(v_ibs_uf) AS uf, sum(v_ibs_mun) AS mun, sum(v_ibs) AS ibs,
                     sum(v_cbs) AS cbs, sum(v_ibs_mono) AS imono, sum(v_cbs_mono) AS cmono,
                     bool_or(ibscbs_presente) AS tem
              FROM itens GROUP BY chave
            ), n AS (SELECT * FROM notas WHERE tot_presente)
            SELECT * FROM (
              SELECT n.chave, NULL AS n_item, 'tot vBCIBSCBS' AS campo, n.tot_v_bc_ibscbs AS valor_declarado,
                     s.vbc AS valor_esperado, 'Soma dos itens' AS detalhe FROM n JOIN s USING (chave) WHERE s.tem
              UNION ALL SELECT n.chave, NULL, 'tot vIBSUF', n.tot_v_ibs_uf, s.uf, 'Soma dos itens' FROM n JOIN s USING (chave) WHERE s.tem
              UNION ALL SELECT n.chave, NULL, 'tot vIBSMun', n.tot_v_ibs_mun, s.mun, 'Soma dos itens' FROM n JOIN s USING (chave) WHERE s.tem
              UNION ALL SELECT n.chave, NULL, 'tot vIBS', n.tot_v_ibs, s.ibs, 'Soma dos itens' FROM n JOIN s USING (chave) WHERE s.tem
              UNION ALL SELECT n.chave, NULL, 'tot vCBS', n.tot_v_cbs, s.cbs, 'Soma dos itens' FROM n JOIN s USING (chave) WHERE s.tem
              UNION ALL SELECT n.chave, NULL, 'tot vIBSMono', n.tot_v_ibs_mono, s.imono, 'Soma dos itens'
                        FROM n JOIN s USING (chave) WHERE s.imono IS NOT NULL OR n.tot_v_ibs_mono IS NOT NULL
              UNION ALL SELECT n.chave, NULL, 'tot vCBSMono', n.tot_v_cbs_mono, s.cmono, 'Soma dos itens'
                        FROM n JOIN s USING (chave) WHERE s.cmono IS NOT NULL OR n.tot_v_cbs_mono IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R014", titulo="Base de cálculo diferente da composição esperada", bloco="ESTRUTURA", severidade="MEDIA",
        financeira=False,
        descricao="vBC do IBS/CBS diferente da composição configurada (regras.base_calculo). Composição a validar com o Tributário.",
        fundamento="LC 214/2025, art. 12 (base de cálculo) e regras de validação da NT 2025.002.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vBC' AS campo, v_bc AS valor_declarado, round($expr_base, 2) AS valor_esperado,
                     'vProd ' || coalesce(v_prod, 0) || ', ICMS ' || coalesce(v_icms, 0) || ', PIS ' || coalesce(v_pis, 0)
                       || ', COFINS ' || coalesce(v_cofins, 0) AS detalhe
              FROM itens WHERE ibscbs_presente AND v_bc IS NOT NULL AND NOT coalesce(tem_mono, false)
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R015", titulo="Monofásico: valor diferente de quantidade x ad rem", bloco="ESTRUTURA", severidade="ALTA",
        financeira=True,
        descricao="Combustíveis (tributação monofásica): vIBSMono/vCBSMono (padrão, retenção e retido) diferente de quantidade x alíquota ad rem.",
        fundamento="LC 214/2025 - regime específico de combustíveis; NT 2025.002 - grupo gIBSCBSMono.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIBSMono' AS campo, v_ibs_mono AS valor_declarado,
                     round(q_bc_mono * ad_rem_ibs, 2) AS valor_esperado,
                     'qBCMono ' || q_bc_mono || ' x adRemIBS ' || ad_rem_ibs AS detalhe
              FROM itens WHERE tem_mono AND q_bc_mono IS NOT NULL AND ad_rem_ibs IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vCBSMono', v_cbs_mono, round(q_bc_mono * ad_rem_cbs, 2),
                     'qBCMono ' || q_bc_mono || ' x adRemCBS ' || ad_rem_cbs
              FROM itens WHERE tem_mono AND q_bc_mono IS NOT NULL AND ad_rem_cbs IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vIBSMonoReten', v_ibs_mono_reten, round(q_bc_mono_reten * ad_rem_ibs_reten, 2),
                     'qBCMonoReten ' || q_bc_mono_reten || ' x adRemIBSReten ' || ad_rem_ibs_reten
              FROM itens WHERE tem_mono AND q_bc_mono_reten IS NOT NULL AND ad_rem_ibs_reten IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vCBSMonoReten', v_cbs_mono_reten, round(q_bc_mono_reten * ad_rem_cbs_reten, 2),
                     'qBCMonoReten ' || q_bc_mono_reten || ' x adRemCBSReten ' || ad_rem_cbs_reten
              FROM itens WHERE tem_mono AND q_bc_mono_reten IS NOT NULL AND ad_rem_cbs_reten IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vIBSMonoRet', v_ibs_mono_ret, round(q_bc_mono_ret * ad_rem_ibs_ret, 2),
                     'qBCMonoRet ' || q_bc_mono_ret || ' x adRemIBSRet ' || ad_rem_ibs_ret
              FROM itens WHERE tem_mono AND q_bc_mono_ret IS NOT NULL AND ad_rem_ibs_ret IS NOT NULL
              UNION ALL
              SELECT chave, n_item, 'vCBSMonoRet', v_cbs_mono_ret, round(q_bc_mono_ret * ad_rem_cbs_ret, 2),
                     'qBCMonoRet ' || q_bc_mono_ret || ' x adRemCBSRet ' || ad_rem_cbs_ret
              FROM itens WHERE tem_mono AND q_bc_mono_ret IS NOT NULL AND ad_rem_cbs_ret IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R016", titulo="Alíquota nominal diferente da alíquota de referência vigente", bloco="ESTRUTURA",
        severidade="MEDIA",
        descricao="pIBSUF/pIBSMun/pCBS diferente da alíquota de referência vigente (antes de reduções) para a data e o local.",
        fundamento="LC 214/2025 - alíquotas de referência e período de transição (2026: ano-teste).",
        sql="""
            WITH ref AS (
              SELECT i.chave, i.n_item, a.tributo, a.aliquota,
                     row_number() OVER (PARTITION BY i.chave, i.n_item, a.tributo
                                        ORDER BY (a.uf <> '*')::INT + 2 * (a.c_mun <> '*')::INT DESC) AS rk
              FROM itens i JOIN ref_aliquotas a
                ON i.dt_emi BETWEEN a.ini_vigencia AND coalesce(a.fim_vigencia, DATE '9999-12-31')
               AND a.uf IN ('*', i.uf_calc) AND a.c_mun IN ('*', i.c_mun_calc)
              WHERE i.ibscbs_presente
            ), r AS (SELECT * FROM ref WHERE rk = 1)
            SELECT * FROM (
              SELECT i.chave, i.n_item, 'pIBSUF' AS campo, i.p_ibs_uf AS valor_declarado, r.aliquota AS valor_esperado,
                     'Referência vigente em ' || i.dt_emi || ' (' || i.uf_calc || ')' AS detalhe
              FROM itens i JOIN r ON r.chave = i.chave AND r.n_item = i.n_item AND r.tributo = 'IBS_UF'
              WHERE i.p_ibs_uf IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'pIBSMun', i.p_ibs_mun, r.aliquota,
                     'Referência vigente em ' || i.dt_emi || ' (' || i.c_mun_calc || ')'
              FROM itens i JOIN r ON r.chave = i.chave AND r.n_item = i.n_item AND r.tributo = 'IBS_MUN'
              WHERE i.p_ibs_mun IS NOT NULL
              UNION ALL
              SELECT i.chave, i.n_item, 'pCBS', i.p_cbs, r.aliquota, 'Referência vigente em ' || i.dt_emi
              FROM itens i JOIN r ON r.chave = i.chave AND r.n_item = i.n_item AND r.tributo = 'CBS'
              WHERE i.p_cbs IS NOT NULL
            ) WHERE fora_tol_aliq(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R017", titulo="Imposto Seletivo: valor diferente do cálculo", bloco="ESTRUTURA", severidade="ALTA",
        financeira=True,
        descricao="vIS diferente de vBCIS x pIS (+ quantidade x alíquota específica).",
        fundamento="LC 214/2025 - Imposto Seletivo; NT 2025.002 - grupo IS.",
        sql="""
            SELECT * FROM (
              SELECT chave, n_item, 'vIS' AS campo, v_is AS valor_declarado,
                     round(coalesce(v_bc_is, 0) * coalesce(p_is, 0) / 100
                           + coalesce(q_trib_is, 0) * coalesce(p_is_espec, 0), 2) AS valor_esperado,
                     'vBCIS ' || coalesce(v_bc_is, 0) || ' x pIS ' || coalesce(p_is, 0) AS detalhe
              FROM itens WHERE is_presente AND v_is IS NOT NULL
            ) WHERE fora_tol(valor_declarado, valor_esperado)
        """,
    ),
    Regra(
        id="R018", titulo="Totalizador IBSCBSTot ausente", bloco="ESTRUTURA", severidade="ALTA",
        descricao="A nota tem itens com IBSCBS, mas não traz o grupo de totais IBSCBSTot.",
        fundamento="NT 2025.002 - grupo W03 (IBSCBSTot).",
        sql="""
            SELECT n.chave, NULL AS n_item, 'IBSCBSTot' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'Itens com IBSCBS e nota sem IBSCBSTot' AS detalhe
            FROM notas n
            WHERE NOT coalesce(n.tot_presente, false)
              AND EXISTS (SELECT 1 FROM itens i WHERE i.chave = n.chave AND i.ibscbs_presente)
        """,
    ),
    Regra(
        id="R019", titulo="Chave de acesso duplicada na base", bloco="ESTRUTURA", severidade="BAIXA",
        descricao="A mesma NF-e aparece mais de uma vez (fontes ou datas diferentes). As demais regras consideram uma única cópia.",
        fundamento="Integridade da base auditada.",
        sql="""
            SELECT chave, NULL AS n_item, 'chave' AS campo, count(*)::DOUBLE AS valor_declarado, 1.0 AS valor_esperado,
                   'Presente ' || count(*) || ' vezes (fontes: ' || string_agg(DISTINCT fonte, ', ') || ')' AS detalhe
            FROM notas_todas GROUP BY chave HAVING count(*) > 1
        """,
    ),
]
