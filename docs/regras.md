# Catálogo de regras

> Gerado por `python scripts/gerar_docs.py` a partir de `src/auditoria_rt/rules/`. Não edite à mão.

Severidade padrão pode ser alterada em `regras.severidade` e regras podem ser desligadas em `regras.desabilitadas` (config). Regras *financeiras* somam |diferença| no impacto do relatório.

## A - Estrutura e consistência interna (sem calculadora)

| Regra | Severidade | Financeira | Título |
|---|---|---|---|
| R000 | ALTA | Não | XML inválido ou não processável |
| R001 | ALTA | Não | Grupo IBSCBS ausente no item |
| R002 | ALTA | Não | CST de IBS/CBS inexistente |
| R003 | ALTA | Não | cClassTrib inexistente ou incompatível com o CST |
| R004 | ALTA | Não | cClassTrib fora da vigência |
| R005 | ALTA | Não | Grupo exigido pela classificação ausente |
| R006 | MEDIA | Não | Grupo não permitido pela classificação |
| R007 | ALTA | Não | Alíquota efetiva inconsistente com o percentual de redução |
| R008 | ALTA | Não | Percentual de redução diferente do previsto na classificação |
| R009 | ALTA | Sim | vIBSUF diferente de vBC x alíquota |
| R010 | ALTA | Sim | vIBSMun diferente de vBC x alíquota |
| R011 | ALTA | Sim | vCBS diferente de vBC x alíquota |
| R012 | ALTA | Sim | vIBS diferente de vIBSUF + vIBSMun |
| R013 | ALTA | Sim | Totais IBSCBSTot diferentes da soma dos itens |
| R014 | MEDIA | Não | Base de cálculo diferente da composição esperada |
| R015 | ALTA | Sim | Monofásico: valor diferente de quantidade x ad rem |
| R016 | MEDIA | Não | Alíquota nominal diferente da alíquota de referência vigente |
| R017 | ALTA | Sim | Imposto Seletivo: valor diferente do cálculo |
| R018 | ALTA | Não | Totalizador IBSCBSTot ausente |
| R019 | BAIXA | Não | Chave de acesso duplicada na base |

### R000 - XML inválido ou não processável

O XML extraído do SAP não pôde ser lido (malformado, sem infNFe, sem itens ou codificação desconhecida).

*Fundamento:* Integridade da base auditada.

### R001 - Grupo IBSCBS ausente no item

Item emitido a partir da data de obrigatoriedade configurada sem o grupo IBSCBS.

*Fundamento:* NT 2025.002 - grupo UB (IBSCBS) do item; LC 214/2025.

### R002 - CST de IBS/CBS inexistente

CST informado não consta na tabela oficial de classificação tributária.

*Fundamento:* Tabela de CST/cClassTrib (anexo da NT 2025.002).

### R003 - cClassTrib inexistente ou incompatível com o CST

O código de classificação tributária não existe ou não pertence ao CST informado.

*Fundamento:* Tabela de CST/cClassTrib (anexo da NT 2025.002).

### R004 - cClassTrib fora da vigência

A classificação existe, mas não estava vigente na data de emissão.

*Fundamento:* Vigência da tabela de cClassTrib.

### R005 - Grupo exigido pela classificação ausente

A classificação exige um grupo (redução, diferimento, monofásico, tributação regular, crédito presumido) que não foi informado.

*Fundamento:* Indicadores de grupos da tabela de cClassTrib.

### R006 - Grupo não permitido pela classificação

O item traz um grupo que a classificação tributária não admite (ex.: redução em operação de tributação integral).

*Fundamento:* Indicadores de grupos da tabela de cClassTrib.

### R007 - Alíquota efetiva inconsistente com o percentual de redução

pAliqEfet diferente de alíquota x (1 - pRedAliq/100) no grupo de redução.

*Fundamento:* NT 2025.002 - grupo gRed.

### R008 - Percentual de redução diferente do previsto na classificação

pRedAliq informado difere do percentual de redução da tabela de cClassTrib.

*Fundamento:* Tabela de cClassTrib (pRedIBS/pRedCBS); LC 214/2025 - reduções.

### R009 - vIBSUF diferente de vBC x alíquota

Valor do IBS estadual não confere com base x alíquota (efetiva, se houver redução), deduzidos diferimento e devolução.

*Fundamento:* NT 2025.002 - regras de cálculo do grupo gIBSUF.

### R010 - vIBSMun diferente de vBC x alíquota

Valor do IBS municipal não confere com base x alíquota, deduzidos diferimento e devolução.

*Fundamento:* NT 2025.002 - regras de cálculo do grupo gIBSMun.

### R011 - vCBS diferente de vBC x alíquota

Valor da CBS não confere com base x alíquota, deduzidos diferimento e devolução.

*Fundamento:* NT 2025.002 - regras de cálculo do grupo gCBS.

### R012 - vIBS diferente de vIBSUF + vIBSMun

O total de IBS do item não é a soma das parcelas estadual e municipal.

*Fundamento:* NT 2025.002 - campo vIBS.

### R013 - Totais IBSCBSTot diferentes da soma dos itens

Totalizadores da nota (vBCIBSCBS, vIBSUF, vIBSMun, vIBS, vCBS, monofásico) não conferem com a soma dos itens.

*Fundamento:* NT 2025.002 - grupo W03 (IBSCBSTot).

### R014 - Base de cálculo diferente da composição esperada

vBC do IBS/CBS diferente da composição configurada (regras.base_calculo). Composição a validar com o Tributário.

*Fundamento:* LC 214/2025, art. 12 (base de cálculo) e regras de validação da NT 2025.002.

### R015 - Monofásico: valor diferente de quantidade x ad rem

Combustíveis (tributação monofásica): vIBSMono/vCBSMono (padrão, retenção e retido) diferente de quantidade x alíquota ad rem.

*Fundamento:* LC 214/2025 - regime específico de combustíveis; NT 2025.002 - grupo gIBSCBSMono.

### R016 - Alíquota nominal diferente da alíquota de referência vigente

pIBSUF/pIBSMun/pCBS diferente da alíquota de referência vigente (antes de reduções) para a data e o local.

*Fundamento:* LC 214/2025 - alíquotas de referência e período de transição (2026: ano-teste).

### R017 - Imposto Seletivo: valor diferente do cálculo

vIS diferente de vBCIS x pIS (+ quantidade x alíquota específica).

*Fundamento:* LC 214/2025 - Imposto Seletivo; NT 2025.002 - grupo IS.

### R018 - Totalizador IBSCBSTot ausente

A nota tem itens com IBSCBS, mas não traz o grupo de totais IBSCBSTot.

*Fundamento:* NT 2025.002 - grupo W03 (IBSCBSTot).

### R019 - Chave de acesso duplicada na base

A mesma NF-e aparece mais de uma vez (fontes ou datas diferentes). As demais regras consideram uma única cópia.

*Fundamento:* Integridade da base auditada.

## B - Aderência à regra (calculadora)

| Regra | Severidade | Financeira | Título |
|---|---|---|---|
| C001 | ALTA | Sim | vCBS diferente do recalculado pela calculadora |
| C002 | ALTA | Sim | vIBSUF diferente do recalculado pela calculadora |
| C003 | ALTA | Sim | vIBSMun diferente do recalculado pela calculadora |
| C004 | MEDIA | Não | Alíquota efetiva diferente da calculadora |
| C005 | ALTA | Não | Combinação rejeitada pela calculadora |
| C006 | INFO | Não | Item não recalculado |
| C007 | MEDIA | Não | Amostra: cálculo completo diverge do atalho por alíquota |
| C008 | ALTA | Sim | Monofásico: valor diferente do ad rem da calculadora |

### C001 - vCBS diferente do recalculado pela calculadora

Valor de CBS declarado diferente de vBC x alíquota efetiva devolvida pela calculadora (deduzidos diferimento e devolução declarados).

*Fundamento:* Calculadora oficial de IBS/CBS (RFB/CGIBS); LC 214/2025.

### C002 - vIBSUF diferente do recalculado pela calculadora

Valor de IBS estadual declarado diferente de vBC x alíquota efetiva devolvida pela calculadora (deduzidos diferimento e devolução declarados).

*Fundamento:* Calculadora oficial de IBS/CBS (RFB/CGIBS); LC 214/2025.

### C003 - vIBSMun diferente do recalculado pela calculadora

Valor de IBS municipal declarado diferente de vBC x alíquota efetiva devolvida pela calculadora (deduzidos diferimento e devolução declarados).

*Fundamento:* Calculadora oficial de IBS/CBS (RFB/CGIBS); LC 214/2025.

### C004 - Alíquota efetiva diferente da calculadora

Alíquota efetiva declarada (pAliqEfet ou alíquota nominal) diferente da devolvida pela calculadora para a mesma data, local, NCM e classificação.

*Fundamento:* Calculadora oficial de IBS/CBS.

### C005 - Combinação rejeitada pela calculadora

A calculadora recusou a combinação de data, local, NCM, CST e cClassTrib do item (ex.: classificação não aplicável ao NCM).

*Fundamento:* Calculadora oficial de IBS/CBS.

### C006 - Item não recalculado

O item não tem resultado da calculadora (indisponibilidade ou etapa de cálculo não executada). Não é desvio fiscal: indica cobertura incompleta da auditoria.

*Fundamento:* Cobertura da auditoria.

### C007 - Amostra: cálculo completo diverge do atalho por alíquota

Validação metodológica: na amostra, o valor calculado item a item pela calculadora difere do valor obtido aplicando a alíquota em cache. Indica que a alíquota depende de outro parâmetro (revisar chave do cache).

*Fundamento:* Controle de qualidade da metodologia (premissa P-01).

### C008 - Monofásico: valor diferente do ad rem da calculadora

vIBSMono/vCBSMono diferente de quantidade x alíquota ad rem devolvida pela calculadora.

*Fundamento:* LC 214/2025 - combustíveis; calculadora oficial.

## C - Padrões nos dados

| Regra | Severidade | Financeira | Título |
|---|---|---|---|
| P001 | BAIXA | Não | Classificação minoritária para o NCM |
| P002 | BAIXA | Não | Mesmo produto com tratamentos diferentes no período |

### P001 - Classificação minoritária para o NCM

Combinação CST/cClassTrib usada em uma fração dos itens do NCM abaixo do limiar configurado (regras.padroes.limiar_minoritario), apenas para NCM com volume mínimo. Indício de classificação incorreta: triagem com o Tributário.

*Fundamento:* Análise de consistência de tratamento (auditoria interna).

### P002 - Mesmo produto com tratamentos diferentes no período

O mesmo produto (emitente + código do produto + NCM) foi tributado com mais de uma combinação CST/cClassTrib no período.

*Fundamento:* Análise de consistência de tratamento (auditoria interna).

## D - Expectativa interna (matriz do Tributário)

| Regra | Severidade | Financeira | Título |
|---|---|---|---|
| E001 | ALTA | Não | Classificação diferente da esperada pela matriz interna |

### E001 - Classificação diferente da esperada pela matriz interna

CST/cClassTrib do item difere do definido pelo Tributário na matriz de expectativa (NCM por prefixo, CFOP e tipo de operação; vale a linha mais específica).

*Fundamento:* Matriz de expectativa da Petrobras (config/referencia/matriz_expectativa.csv).
