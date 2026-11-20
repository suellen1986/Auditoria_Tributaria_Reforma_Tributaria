# Premissas e decisões de metodologia

Registro para a Auditoria Interna. Cada premissa tem responsável pela validação e status.
Atualize a cada rodada de triagem.

| ID | Premissa | Onde está no código | Validar com | Status |
|---|---|---|---|---|
| P-01 | A alíquota efetiva de IBS/CBS de um item depende só de: data (mês, por padrão), UF, município, NCM, CST, cClassTrib (e unidade, no monofásico). Por isso a calculadora é consultada uma vez por combinação e a alíquota é aplicada a todos os itens. A regra C007 testa isso numa amostra aleatória a cada execução. | `calc/orquestrador.py`, `workspace.py` (view `itens_calc`) | TI + Tributário | A validar |
| P-02 | Composição da base de cálculo (R014): vProd + vFrete + vSeg + vOutro − vDesc − vICMS − vPIS − vCOFINS (IPI peso 0). | `config.yaml` → `regras.base_calculo` | Tributário | **A validar** |
| P-03 | Local da operação para o IBS: UF = entrega → destinatário → emitente; município = cMunFGIBS → entrega → destinatário → cMunFG. | `workspace.py` (view `itens`) | Tributário | A validar |
| P-04 | Valor esperado do tributo = round(vBC × alíquota efetiva / 100, 2) − vDif − vDevTrib, com alíquota efetiva = pAliqEfet (se houver gRed) ou a alíquota nominal. | `rules/estrutura.py` R009–R011, `rules/calculo.py` C001–C003 | Tributário | A validar |
| P-05 | Monofásico: valor = round(quantidade × ad rem, 2) para os grupos padrão, retenção e retido. | R015, C008 | Tributário | A validar |
| P-06 | Notas duplicadas na base (mesma chave): as regras usam uma única cópia (menor fonte/hash); R019 aponta a duplicidade. | `workspace.py` | Auditoria | Definido |
| P-07 | Impacto financeiro: soma de \|declarado − esperado\| das regras financeiras, sem dupla contagem por (nota, item, campo). É estimativa de exposição, não valor a recolher. | `report/excel.py` | Auditoria | Definido |
| P-08 | 2026 é ano-teste: CBS 0,9% e IBS 0,1% (estadual 0,1%, municipal 0%). Conferir com a legislação e as tabelas da calculadora. | `config/referencia/aliquotas_referencia.csv` | Tributário | A validar |
| P-09 | Valores monetários são processados em ponto flutuante (double) e comparados com arredondamento a 2 casas e tolerância ≥ R$ 0,01. | regras | Auditoria | Definido |
| P-10 | Notas canceladas, denegadas ou substituídas: o MVP não lê eventos. Use `filtro_extra` na extração para trazer só autorizadas. | `config.yaml` → `filtro_extra` | TI SAP | A definir |
