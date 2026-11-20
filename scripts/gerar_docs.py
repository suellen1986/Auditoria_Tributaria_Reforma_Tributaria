"""Gera docs/regras.md a partir do catálogo de regras do código (fonte única)."""

from pathlib import Path

from auditoria_rt.rules.base import todas

BLOCOS = {
    "ESTRUTURA": "A - Estrutura e consistência interna (sem calculadora)",
    "CALCULO": "B - Aderência à regra (calculadora)",
    "PADRAO": "C - Padrões nos dados",
    "EXPECTATIVA": "D - Expectativa interna (matriz do Tributário)",
}


def main() -> None:
    linhas = [
        "# Catálogo de regras",
        "",
        "> Gerado por `python scripts/gerar_docs.py` a partir de `src/auditoria_rt/rules/`. Não edite à mão.",
        "",
        "Severidade padrão pode ser alterada em `regras.severidade` e regras podem ser desligadas em "
        "`regras.desabilitadas` (config). Regras *financeiras* somam |diferença| no impacto do relatório.",
        "",
    ]
    regras = todas()
    for bloco, titulo in BLOCOS.items():
        linhas += [f"## {titulo}", "", "| Regra | Severidade | Financeira | Título |", "|---|---|---|---|"]
        for r in regras:
            if r.bloco == bloco:
                linhas.append(f"| {r.id} | {r.severidade} | {'Sim' if r.financeira else 'Não'} | {r.titulo} |")
        linhas.append("")
        for r in regras:
            if r.bloco == bloco:
                linhas += [f"### {r.id} - {r.titulo}", "", r.descricao, "", f"*Fundamento:* {r.fundamento}", ""]
    out = Path(__file__).resolve().parents[1] / "docs" / "regras.md"
    out.write_text("\n".join(linhas), encoding="utf-8")
    print(f"Gerado {out}")


if __name__ == "__main__":
    main()
