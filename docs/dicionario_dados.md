# Dicionário de dados

Esquemas definidos em `src/auditoria_rt/parse/esquema.py`. Valores monetários em R$ e alíquotas em %.

## itens (1 linha por item de NF-e)

| Campo | Origem no XML | Observação |
|---|---|---|
| chave, n_item | `infNFe@Id`, `det@nItem` | chave da linha |
| fonte, lote, hash_xml | extração | rastreabilidade (SHA-256 do XML) |
| dt_emi, mod, tp_nf, fin_nfe | `ide/dhEmi`, `mod`, `tpNF`, `finNFe` | |
| cnpj_emit, uf_emit, c_mun_emit | `emit` | |
| cnpj_dest, uf_dest, c_mun_dest | `dest` (CNPJ/CPF/idEstrangeiro) | |
| uf_entrega, c_mun_entrega | `entrega` | |
| c_mun_fg, c_mun_fg_ibs | `ide/cMunFG`, `ide/cMunFGIBS` | |
| c_prod, x_prod, ncm, cest, cfop, u_com, q_com, u_trib, q_trib | `prod` | |
| v_prod, v_frete, v_seg, v_desc, v_outro | `prod` | |
| v_icms, v_icms_st, v_ipi, v_pis, v_cofins | `imposto/ICMS`, `IPI`, `PIS`, `COFINS` | usados na composição da base (R014) |
| ibscbs_presente | existência de `imposto/IBSCBS` | |
| cst, cclasstrib | `IBSCBS/CST`, `IBSCBS/cClassTrib` | |
| v_bc | `gIBSCBS/vBC` | |
| p_ibs_uf, p_dif_uf, v_dif_uf, v_dev_trib_uf, p_red_aliq_uf, p_aliq_efet_uf, v_ibs_uf | `gIBSUF` (incl. gDif, gDevTrib, gRed) | |
| p_ibs_mun, … , v_ibs_mun | `gIBSMun` | mesmo padrão |
| v_ibs | `gIBSCBS/vIBS` | |
| p_cbs, … , v_cbs | `gCBS` | mesmo padrão |
| tem_g_red, tem_g_dif, tem_g_dev_trib, tem_g_trib_regular, tem_g_cred_pres, tem_g_trib_compra_gov | existência dos grupos | R005/R006 |
| tem_mono, q_bc_mono, ad_rem_ibs, ad_rem_cbs, v_ibs_mono, v_cbs_mono, *_reten, *_ret | `gIBSCBSMono` | combustíveis |
| is_presente, cst_is, cclasstrib_is, v_bc_is, p_is, p_is_espec, u_trib_is, q_trib_is, v_is | `imposto/IS` | Imposto Seletivo |

Colunas calculadas na view `itens`: `uf_calc`, `c_mun_calc` (premissa P-03), `dt_calc`
(chave de data do cache) e `u_trib_calc`.

## notas (1 linha por NF-e)

chave, fonte, versao_leiaute, mod, serie, n_nf, tp_nf, fin_nfe, dh_emi, dt_emi, emitente e
destinatário (CNPJ, nome, UF), qtd_itens, v_nf e os totais `IBSCBSTot`: tot_v_bc_ibscbs,
tot_v_ibs_uf, tot_v_ibs_mun, tot_v_ibs, tot_v_cbs, tot_v_ibs_mono, tot_v_cbs_mono, além de `ISTot/vIS`.

## erros

XMLs não processáveis: chave_origem, fonte, dt_ref, erro, hash_xml, lote → regra R000.

## Tabelas no `auditoria.duckdb`

| Tabela | Conteúdo |
|---|---|
| ref_class_trib, ref_aliquotas, ref_matriz | referências carregadas dos CSVs |
| ref_versoes | arquivo, SHA-256, linhas e data de carga de cada referência |
| calc_aliquotas | cache da calculadora por combinação de parâmetros e versão |
| calc_amostra | cálculo completo dos itens da amostra (por execução) |
| desvios | execucao, regra, severidade, bloco, chave, n_item, campo, valor_declarado, valor_esperado, diferenca, impacto, detalhe |
| execucoes, execucao_regras | histórico das execuções e tempo e status de cada regra |
