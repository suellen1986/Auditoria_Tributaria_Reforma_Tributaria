"""Blocos C (padrões nos dados) e D (expectativa interna da Petrobras)."""

from auditoria_rt.rules.base import Regra

REGRAS = [
    Regra(
        id="P001", titulo="Classificação minoritária para o NCM", bloco="PADRAO", severidade="BAIXA",
        descricao="Combinação CST/cClassTrib usada em uma fração dos itens do NCM abaixo do limiar configurado "
                  "(regras.padroes.limiar_minoritario), apenas para NCM com volume mínimo. "
                  "Indício de classificação incorreta: triagem com o Tributário.",
        fundamento="Análise de consistência de tratamento (auditoria interna).",
        sql="""
            WITH f AS (
              SELECT ncm, cst, coalesce(cclasstrib, '') AS cc, count(*) AS n
              FROM itens WHERE ibscbs_presente AND ncm IS NOT NULL GROUP BY ALL
            ), t AS (
              SELECT ncm, sum(n) AS total, arg_max(cst || '/' || cc, n) AS dominante FROM f GROUP BY ncm
            )
            SELECT i.chave, i.n_item, 'CST/cClassTrib' AS campo, f.n::DOUBLE / t.total AS valor_declarado,
                   NULL AS valor_esperado,
                   'NCM ' || i.ncm || ': ' || i.cst || '/' || coalesce(i.cclasstrib, '') || ' em '
                     || round(100.0 * f.n / t.total, 2) || '% de ' || t.total || ' itens; dominante ' || t.dominante AS detalhe
            FROM itens i
            JOIN f ON f.ncm = i.ncm AND f.cst = i.cst AND f.cc = coalesce(i.cclasstrib, '')
            JOIN t ON t.ncm = i.ncm
            WHERE i.ibscbs_presente AND t.total >= $min_itens_ncm AND f.n::DOUBLE / t.total < $limiar_minoritario
        """,
    ),
    Regra(
        id="P002", titulo="Mesmo produto com tratamentos diferentes no período", bloco="PADRAO", severidade="BAIXA",
        descricao="O mesmo produto (emitente + código do produto + NCM) foi tributado com mais de uma combinação CST/cClassTrib no período.",
        fundamento="Análise de consistência de tratamento (auditoria interna).",
        sql="""
            WITH p AS (
              SELECT cnpj_emit, c_prod, ncm, count(DISTINCT cst || '/' || coalesce(cclasstrib, '')) AS combos,
                     string_agg(DISTINCT cst || '/' || coalesce(cclasstrib, ''), ', ') AS lista
              FROM itens WHERE ibscbs_presente AND c_prod IS NOT NULL GROUP BY ALL
              HAVING count(DISTINCT cst || '/' || coalesce(cclasstrib, '')) > 1
            )
            SELECT i.chave, i.n_item, 'CST/cClassTrib' AS campo, p.combos::DOUBLE AS valor_declarado, 1.0 AS valor_esperado,
                   'Produto ' || i.c_prod || ' (NCM ' || coalesce(i.ncm, '-') || ') com: ' || p.lista AS detalhe
            FROM itens i JOIN p ON p.cnpj_emit = i.cnpj_emit AND p.c_prod = i.c_prod AND p.ncm IS NOT DISTINCT FROM i.ncm
            WHERE i.ibscbs_presente
        """,
    ),
    Regra(
        id="E001", titulo="Classificação diferente da esperada pela matriz interna", bloco="EXPECTATIVA",
        severidade="ALTA",
        descricao="CST/cClassTrib do item difere do definido pelo Tributário na matriz de expectativa "
                  "(NCM por prefixo, CFOP e tipo de operação; vale a linha mais específica).",
        fundamento="Matriz de expectativa da Petrobras (config/referencia/matriz_expectativa.csv).",
        sql="""
            WITH m AS (
              SELECT i.chave, i.n_item, i.ncm, i.cfop, i.cst, i.cclasstrib,
                     r.cst_esperado, r.cclasstrib_esperado, r.observacao,
                     row_number() OVER (PARTITION BY i.chave, i.n_item
                                        ORDER BY length(r.ncm_prefixo) DESC, (r.cfop <> '*')::INT DESC,
                                                 (r.tp_nf <> '*')::INT DESC) AS rk
              FROM itens i JOIN ref_matriz r
                ON starts_with(coalesce(i.ncm, ''), r.ncm_prefixo)
               AND r.cfop IN ('*', i.cfop) AND r.tp_nf IN ('*', i.tp_nf)
            )
            SELECT chave, n_item, 'CST/cClassTrib' AS campo, NULL AS valor_declarado, NULL AS valor_esperado,
                   'Esperado ' || cst_esperado || '/' || coalesce(cclasstrib_esperado, '*') || ', declarado '
                     || coalesce(cst, '(sem IBSCBS)') || '/' || coalesce(cclasstrib, '-')
                     || ' (NCM ' || coalesce(ncm, '-') || ', CFOP ' || coalesce(cfop, '-') || '). '
                     || coalesce(observacao, '') AS detalhe
            FROM m
            WHERE rk = 1 AND (coalesce(cst, '') <> cst_esperado
                   OR (cclasstrib_esperado IS NOT NULL AND coalesce(cclasstrib, '') <> cclasstrib_esperado))
        """,
    ),
]
