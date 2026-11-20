# Implantação no ambiente interno

Checklist na ordem recomendada. Cada passo tem como verificar se deu certo.

## 1. Servidor e Python

- Linux ou Windows com Python 3.10+, e de preferência 16+ núcleos e 64 GB de RAM para milhões de notas/mês.
- Disco: cerca de 3 a 5 KB por NF-e em parquet zstd (bruto + normalizado). 10 milhões de notas ocupam ~50 GB.

### Instalação sem internet

Numa máquina com acesso ao repositório de pacotes (mesmo SO e versão de Python):
```bash
pip download -r requirements.txt -d wheels/
```
Copie `wheels/` e o projeto para o servidor interno:
```bash
pip install --no-index --find-links wheels/ -r requirements.txt
pip install --no-index --find-links wheels/ -e .
```
O `hdbcli` também está no SAP Software Download Center / HANA Client, caso o PyPI seja bloqueado.

**Verificar:** `pytest` passa (o teste `test_resposta_real` é pulado até o passo 4).

## 2. Conexão com o SAP

Em `config/config.yaml` → `extracao.fontes`, crie uma entrada por tabela/visão de XML (ex.: entradas e saídas).

| Campo | O que informar |
|---|---|
| `tipo` | `hana` (driver hdbcli) ou `odbc` (camada de virtualização com driver ODBC) |
| `tabela` | nome completo. Com namespace SAP use aspas: `'"SAPABAP1"."/XNFE/..."'` |
| `colunas.chave` / `data` / `xml` | colunas da chave de 44 dígitos, da data e do XML |
| `colunas.sequencia` | só se o XML estiver quebrado em várias linhas (segmentos); informe a coluna de ordem |
| `formato_data` | `date`, `dats` (AAAAMMDD texto, padrão ABAP) ou `timestamp_dec` (AAAAMMDDhhmmss) |
| `codificacao_xml` | `auto` detecta texto, gzip, zlib, base64 e hex. Fixe o formato se souber |
| `filtro_extra` | ex.: `AND STATUS = '100'` para só autorizadas, ou filtro por empresa/CNPJ |

As senhas ficam em variáveis de ambiente (`SAP_HANA_PASSWORD`), nunca no arquivo.
Peça um **usuário técnico só de leitura**, com acesso apenas à tabela/visão do XML.

**Verificar:** `auditoria-rt testar-conexoes` → `conexão OK; tabela ... acessível`.
Depois extraia um único dia e confira a contagem com o SAP:
```bash
auditoria-rt extrair --de 2026-03-02 --ate 2026-03-02
auditoria-rt processar
```
`processar` informa notas, itens e erros. Se houver erros, veja a regra R000 no relatório
(normalmente é a `codificacao_xml` ou o XML em segmentos).

## 3. Calculadora local

1. Suba a calculadora a partir do código liberado (container ou jar) num servidor interno.
2. Em `config.yaml` → `calculadora`: `modo: http`, `url_base`, `endpoint_calculo` e **`versao`**
   (vai para o relatório; mude-a sempre que atualizar a calculadora ou as tabelas dela, o que invalida o cache).
3. Ajuste a capacidade: `workers` (requisições simultâneas) e `itens_por_requisicao`.
   Para mais vazão, rode várias instâncias atrás de um balanceador.

**Enquanto a calculadora não estiver no ar** use `modo: tabela`: o pipeline roda
com as alíquotas de referência e as reduções da tabela de cClassTrib.

## 4. Contrato da calculadora (único ponto de código a ajustar)

`src/auditoria_rt/calc/contrato.py` monta a requisição e lê a resposta.

1. Faça uma chamada manual à calculadora com um item (ex.: com `curl`) e salve a resposta em
   `tests/fixtures/resposta_calculadora.json`.
2. Rode `pytest tests/test_contrato.py`. Se `test_resposta_real` falhar, ajuste `montar_requisicao`
   (nomes dos campos de entrada) e/ou `ler_resposta`.
   A leitura já busca recursivamente `pIBSUF`/`vIBSUF`/`pIBSMun`/`vIBSMun`/`pCBS`/`vCBS`/`vIBSMono`/`vCBSMono`,
   e costuma funcionar sem mudanças se a resposta seguir o leiaute da NF-e.
3. `auditoria-rt testar-conexoes` → `[calculadora] OK`.

## 5. Tabelas de referência

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `classificacao_tributaria.csv` | CST, cClassTrib, % de redução, indicadores de grupos (OBRIGATORIO/PERMITIDO/PROIBIDO), vigência | **Tabela oficial** de cClassTrib (anexo da NT / tabelas da própria calculadora). A do repositório é EXEMPLO |
| `aliquotas_referencia.csv` | alíquotas por tributo, UF e município (`*` = todos), com vigência | Legislação / tabelas da calculadora |
| `matriz_expectativa.csv` | NCM (prefixo) × CFOP × tpNF → CST/cClassTrib esperado | Tributário da Petrobras (comece pelos produtos de maior valor) |

Enquanto houver linhas `origem=EXEMPLO`, o relatório mostra um ALERTA de resultado não conclusivo.

**Verificar:** `auditoria-rt referencias` mostra as contagens. O hash de cada arquivo vai para a aba Leia-me.

## 6. Parâmetros acordados com a Auditoria Interna

- `regras.tolerancia_abs` / `tolerancia_rel` / `tolerancia_aliquota`
- `regras.base_calculo`: composição da vBC (**validar com o Tributário**, premissa P-02)
- `regras.ibscbs_obrigatorio_desde`
- `regras.severidade` / `regras.desabilitadas`

## 7. Primeira rodada (piloto)

```bash
auditoria-rt executar --de 2026-03-01 --ate 2026-03-07
```
Triagem do resultado com o Tributário: falsos positivos viram ajuste de parâmetro ou de
regra, e os verdadeiros viram achados. Registre as decisões em `docs/premissas.md`.

## 8. Produção (mensal)

```bash
auditoria-rt executar --de 2026-03-01 --ate 2026-03-31
```
Agende no orquestrador corporativo (Control-M, cron, Airflow). Reexecuções são
idempotentes: dias extraídos e arquivos processados são pulados, e a calculadora só
é chamada para combinações novas.

## Solução de problemas

| Sintoma | Causa provável |
|---|---|
| Muitos R000 "XML malformado" | `codificacao_xml` errada, XML em segmentos sem `colunas.sequencia` |
| Muitos C006 (item não recalculado) | calculadora fora do ar (status FALHA não vai para o cache; basta rodar `calcular` de novo) |
| Muitos C005 | contrato da calculadora desajustado (veja a mensagem no detalhe) ou classificações de fato inválidas |
| C007 com desvios | a alíquota depende de outro parâmetro além da chave do cache: use `granularidade_data: dia` ou inclua o campo na chave |
| Memória no DuckDB | reduza `workspace.duckdb_threads` ou aumente `duckdb_memoria` |
