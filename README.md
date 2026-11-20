# Auditoria RT: aderência das NF-e ao IBS/CBS/IS

MVP de auditoria em lote que lê os XMLs de NF-e direto das tabelas do SAP,
valida a estrutura e os cálculos dos grupos da Reforma Tributária (NT 2025.002),
recalcula com a **calculadora oficial rodando localmente** e gera o relatório de
desvios para a **Auditoria Interna**.

Foi feito para milhões de notas: extração particionada por dia e retomável,
parse paralelo, regras em SQL vetorizado (DuckDB) e uso da calculadora por
combinação distinta de parâmetros, com cache.

```
SAP (tabela/visão de XML)
  │ extrair      → workdir/raw/fonte=*/dt=*/part-*.parquet       (1 dia por vez, paralelo, retomável)
  │ processar    → workdir/parsed/{notas,itens,erros}/...         (parse paralelo, 1 processo por arquivo)
  │ calcular     → calc_aliquotas (cache)  + calc_amostra         (calculadora local)
  │ auditar      → desvios                                         (31 regras SQL)
  └ relatório    → workdir/saidas/<execução>/relatorio_*.xlsx, desvios_detalhe.parquet/.csv, manifesto.json
```

## Início rápido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[hana,dev]"           # ou: pip install -r requirements.txt
cp config/config.exemplo.yaml config/config.yaml   # e preencha os pontos ">>> CONEXÃO"

export SAP_HANA_HOST=... SAP_HANA_PORT=... SAP_HANA_USER=... SAP_HANA_PASSWORD=...
auditoria-rt testar-conexoes
auditoria-rt executar --de 2026-01-01 --ate 2026-01-31
```

Sem acesso à rede externa (pacotes offline): veja [docs/implantacao.md](docs/implantacao.md#instalação-sem-internet).

## O que você precisa conectar (resumo)

| # | O quê | Onde |
|---|---|---|
| 1 | Credenciais e tabela/colunas do XML no SAP | `config/config.yaml` → `extracao.fontes` |
| 2 | URL, endpoint e versão da calculadora local | `config/config.yaml` → `calculadora` |
| 3 | Formato de requisição e resposta da calculadora (se diferente) | `src/auditoria_rt/calc/contrato.py` (único arquivo) |
| 4 | **Tabela oficial de CST/cClassTrib** (a do repositório é EXEMPLO) | `config/referencia/classificacao_tributaria.csv` |
| 5 | Alíquotas de referência vigentes | `config/referencia/aliquotas_referencia.csv` |
| 6 | Matriz de expectativa do Tributário (opcional) | `config/referencia/matriz_expectativa.csv` |
| 7 | Tolerâncias e base de cálculo acordadas com a Auditoria | `config/config.yaml` → `regras` |

Passo a passo completo: **[docs/implantacao.md](docs/implantacao.md)**.

## Comandos

| Comando | Faz |
|---|---|
| `testar-conexoes` | testa as fontes SAP e a calculadora |
| `referencias` | carrega as tabelas de referência (registra o hash) |
| `extrair --de --ate [--refazer]` | XML do SAP → parquet, um dia por vez; pula dias já extraídos |
| `processar [--workers N]` | parse dos XMLs; pula arquivos já processados |
| `calcular [--de --ate] [--execucao ID]` | calculadora: combinações distintas + amostra |
| `auditar [--de --ate] [--regras R009 C001] [--execucao ID]` | regras + relatório |
| `executar --de --ate [--sem-extracao]` | tudo, em sequência |
| `catalogo` | lista as regras |

Use o mesmo `--execucao` em `calcular` e `auditar` quando rodar as etapas separadas
(a regra C007 da amostra depende disso). O `executar` já faz isso.

## Regras

São 31 regras em 4 blocos: estrutura (R000–R019), calculadora (C001–C008),
padrões (P001–P002) e expectativa interna (E001). Catálogo completo em
[docs/regras.md](docs/regras.md), gerado do código com `python scripts/gerar_docs.py`.

Nova regra: adicione um `Regra(...)` com uma consulta SQL em `src/auditoria_rt/rules/`.
O motor grava os desvios, mede o tempo e isola falhas (uma regra com erro não para a execução).

## Relatório (Auditoria Interna)

`relatorio_auditoria_<execução>.xlsx` tem as abas Leia-me (metadados, versões e
hashes das referências, tolerâncias, alertas), Resumo por regra, Execução das
regras, Por emitente, Por destinatário, Por NCM, Por mês, Detalhe (top N) e
Catálogo de regras. O detalhe completo sai em `desvios_detalhe.parquet` e `.csv`,
e `manifesto.json` registra a execução para reprodução.

## Desempenho medido (massa sintética, 4 núcleos)

100 mil notas (300 mil itens): parse + cálculo + 31 regras + relatório em cerca de 35 s.
O parse escala linearmente com os núcleos (`--workers`). Para gerar massa de teste:
`python scripts/gerar_massa_sintetica.py --workdir ./workdir_carga --notas 1000000`.

## Testes

```bash
pytest            # parser, decodificação, contrato, cliente HTTP, pipeline ponta a ponta
```

## Segurança e dados

- Os dados ficam no `workdir` local. `.gitignore` bloqueia parquet, xlsx, duckdb e `config/config.yaml`.
- As senhas vêm só de variáveis de ambiente (`${VAR}`) e são mascaradas no hash e no manifesto.
- O parser não resolve entidades externas (proteção contra XXE).
- A calculadora é chamada só no endereço interno configurado (o proxy do ambiente é ignorado por padrão).
