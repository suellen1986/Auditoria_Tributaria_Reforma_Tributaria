"""Gerador de NF-e sintéticas (sem dados reais) para testes e teste de carga.

Gera XML no leiaute 4.00 com os grupos de IBS/CBS da NT 2025.002. Os valores são
calculados de forma consistente, e cada campo pode ser sobrescrito para simular
desvios.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

NS = "http://www.portalfiscal.inf.br/nfe"


def _m(v: float) -> str:
    return f"{v:.2f}"


def _p(v: float) -> str:
    return f"{v:.4f}"


@dataclass
class ItemSint:
    ncm: str = "27101921"
    cfop: str = "5102"
    c_prod: str = "PRD001"
    x_prod: str = "PRODUTO SINTETICO"
    v_prod: float = 1000.0
    q_trib: float = 100.0
    u_trib: str = "L"
    cst: str = "000"
    cclasstrib: str = "000001"
    p_ibs_uf: float = 0.1
    p_ibs_mun: float = 0.0
    p_cbs: float = 0.9
    p_red: float | None = None          # gera gRed com este percentual em UF, Mun e CBS
    p_aliq_efet_cbs: float | None = None  # sobrescreve pAliqEfet da CBS
    p_dif: float | None = None          # gera gDif
    v_bc: float | None = None
    v_ibs_uf: float | None = None
    v_ibs_mun: float | None = None
    v_cbs: float | None = None
    sem_ibscbs: bool = False
    mono: dict | None = None            # {"q": 1000, "ad_rem_ibs": 0.1, "ad_rem_cbs": 0.2, "v_ibs": ..., "v_cbs": ...}

    def calcular(self) -> dict:
        vbc = self.v_bc if self.v_bc is not None else self.v_prod
        fator = 1 - (self.p_red or 0) / 100
        e_uf, e_mun = self.p_ibs_uf * fator, self.p_ibs_mun * fator
        e_cbs = self.p_aliq_efet_cbs if self.p_aliq_efet_cbs is not None else self.p_cbs * fator
        bruto = {"uf": round(vbc * e_uf / 100, 2), "mun": round(vbc * e_mun / 100, 2), "cbs": round(vbc * e_cbs / 100, 2)}
        dif = {k: round(v * (self.p_dif or 0) / 100, 2) for k, v in bruto.items()}
        uf = self.v_ibs_uf if self.v_ibs_uf is not None else bruto["uf"] - dif["uf"]
        mun = self.v_ibs_mun if self.v_ibs_mun is not None else bruto["mun"] - dif["mun"]
        cbs = self.v_cbs if self.v_cbs is not None else bruto["cbs"] - dif["cbs"]
        return {"vbc": vbc, "e_uf": e_uf, "e_mun": e_mun, "e_cbs": e_cbs, "uf": uf, "mun": mun, "cbs": cbs, "dif": dif}


@dataclass
class NotaSint:
    chave: str
    dh_emi: str = "2026-03-10T10:00:00-03:00"
    cnpj_emit: str = "33000167000101"
    x_nome_emit: str = "EMITENTE SINTETICO SA"
    uf_emit: str = "RJ"
    c_mun_emit: str = "3304557"
    cnpj_dest: str = "11111111000191"
    x_nome_dest: str = "DESTINATARIO SINTETICO LTDA"
    uf_dest: str = "SP"
    c_mun_dest: str = "3550308"
    tp_nf: str = "1"
    itens: list[ItemSint] = field(default_factory=lambda: [ItemSint()])
    tot_override: dict = field(default_factory=dict)   # ex.: {"vCBS": 1.23}
    sem_tot: bool = False
    namespace: bool = True


def _g_trib(tag: str, aliq_tag: str, aliq: float, valor: float, it: ItemSint, efet: float, dif: float) -> str:
    x = f"<{tag}><{aliq_tag}>{_p(aliq)}</{aliq_tag}>"
    if it.p_dif is not None:
        x += f"<gDif><pDif>{_p(it.p_dif)}</pDif><vDif>{_m(dif)}</vDif></gDif>"
    if it.p_red is not None:
        x += f"<gRed><pRedAliq>{_p(it.p_red)}</pRedAliq><pAliqEfet>{_p(efet)}</pAliqEfet></gRed>"
    x += f"<v{aliq_tag[1:]}>{_m(valor)}</v{aliq_tag[1:]}></{tag}>"
    return x


def gerar_xml(nota: NotaSint) -> str:
    dets, tot = [], {"vbc": 0.0, "uf": 0.0, "mun": 0.0, "cbs": 0.0, "dif_uf": 0.0, "dif_mun": 0.0, "dif_cbs": 0.0,
                     "imono": 0.0, "cmono": 0.0, "vprod": 0.0}
    tem_mono = False
    for n, it in enumerate(nota.itens, 1):
        c = it.calcular()
        tot["vprod"] += it.v_prod
        ibscbs = ""
        if not it.sem_ibscbs:
            if it.mono:
                tem_mono = True
                m = it.mono
                v_i = m.get("v_ibs", round(m["q"] * m["ad_rem_ibs"], 2))
                v_c = m.get("v_cbs", round(m["q"] * m["ad_rem_cbs"], 2))
                tot["imono"] += v_i
                tot["cmono"] += v_c
                ibscbs = (f"<IBSCBS><CST>{it.cst}</CST><cClassTrib>{it.cclasstrib}</cClassTrib>"
                          f"<gIBSCBSMono><qBCMono>{m['q']:.4f}</qBCMono><adRemIBS>{m['ad_rem_ibs']:.4f}</adRemIBS>"
                          f"<adRemCBS>{m['ad_rem_cbs']:.4f}</adRemCBS><vIBSMono>{_m(v_i)}</vIBSMono>"
                          f"<vCBSMono>{_m(v_c)}</vCBSMono></gIBSCBSMono></IBSCBS>")
            else:
                for k in ("vbc", "uf", "mun", "cbs"):
                    tot[k] += c[k]
                for k in ("uf", "mun", "cbs"):
                    tot["dif_" + k] += c["dif"][k]
                ibscbs = (
                    f"<IBSCBS><CST>{it.cst}</CST><cClassTrib>{it.cclasstrib}</cClassTrib><gIBSCBS>"
                    f"<vBC>{_m(c['vbc'])}</vBC>"
                    + _g_trib("gIBSUF", "pIBSUF", it.p_ibs_uf, c["uf"], it, c["e_uf"], c["dif"]["uf"])
                    + _g_trib("gIBSMun", "pIBSMun", it.p_ibs_mun, c["mun"], it, c["e_mun"], c["dif"]["mun"])
                    + f"<vIBS>{_m(c['uf'] + c['mun'])}</vIBS>"
                    + _g_trib("gCBS", "pCBS", it.p_cbs, c["cbs"], it, c["e_cbs"], c["dif"]["cbs"])
                    + "</gIBSCBS></IBSCBS>"
                )
        dets.append(
            f'<det nItem="{n}"><prod><cProd>{it.c_prod}</cProd><cEAN>SEM GTIN</cEAN><xProd>{it.x_prod}</xProd>'
            f"<NCM>{it.ncm}</NCM><CFOP>{it.cfop}</CFOP><uCom>{it.u_trib}</uCom><qCom>{it.q_trib:.4f}</qCom>"
            f"<vUnCom>{it.v_prod / max(it.q_trib, 1):.10f}</vUnCom><vProd>{_m(it.v_prod)}</vProd>"
            f"<cEANTrib>SEM GTIN</cEANTrib><uTrib>{it.u_trib}</uTrib><qTrib>{it.q_trib:.4f}</qTrib>"
            f"<vUnTrib>{it.v_prod / max(it.q_trib, 1):.10f}</vUnTrib><indTot>1</indTot></prod>"
            f"<imposto>{ibscbs}</imposto></det>"
        )
    o = nota.tot_override
    ibscbs_tot = "" if nota.sem_tot else (
        "<IBSCBSTot>"
        f"<vBCIBSCBS>{_m(o.get('vBCIBSCBS', tot['vbc']))}</vBCIBSCBS>"
        f"<gIBS><gIBSUF><vDif>{_m(tot['dif_uf'])}</vDif><vDevTrib>0.00</vDevTrib><vIBSUF>{_m(o.get('vIBSUF', tot['uf']))}</vIBSUF></gIBSUF>"
        f"<gIBSMun><vDif>{_m(tot['dif_mun'])}</vDif><vDevTrib>0.00</vDevTrib><vIBSMun>{_m(o.get('vIBSMun', tot['mun']))}</vIBSMun></gIBSMun>"
        f"<vIBS>{_m(o.get('vIBS', tot['uf'] + tot['mun']))}</vIBS><vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gIBS>"
        f"<gCBS><vDif>{_m(tot['dif_cbs'])}</vDif><vDevTrib>0.00</vDevTrib><vCBS>{_m(o.get('vCBS', tot['cbs']))}</vCBS>"
        f"<vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gCBS>"
        + (f"<gMono><vIBSMono>{_m(tot['imono'])}</vIBSMono><vCBSMono>{_m(tot['cmono'])}</vCBSMono></gMono>" if tem_mono else "")
        + "</IBSCBSTot>"
    )
    ns = f' xmlns="{NS}"' if nota.namespace else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><nfeProc{ns} versao="4.00"><NFe><infNFe Id="NFe{nota.chave}" versao="4.00">'
        f"<ide><cUF>33</cUF><natOp>VENDA</natOp><mod>55</mod><serie>1</serie><nNF>{int(nota.chave[25:34])}</nNF>"
        f"<dhEmi>{nota.dh_emi}</dhEmi><tpNF>{nota.tp_nf}</tpNF><cMunFG>{nota.c_mun_emit}</cMunFG><finNFe>1</finNFe></ide>"
        f"<emit><CNPJ>{nota.cnpj_emit}</CNPJ><xNome>{nota.x_nome_emit}</xNome>"
        f"<enderEmit><cMun>{nota.c_mun_emit}</cMun><UF>{nota.uf_emit}</UF></enderEmit></emit>"
        f"<dest><CNPJ>{nota.cnpj_dest}</CNPJ><xNome>{nota.x_nome_dest}</xNome>"
        f"<enderDest><cMun>{nota.c_mun_dest}</cMun><UF>{nota.uf_dest}</UF></enderDest></dest>"
        + "".join(dets)
        + f"<total><ICMSTot><vProd>{_m(tot['vprod'])}</vProd><vNF>{_m(tot['vprod'])}</vNF></ICMSTot>{ibscbs_tot}</total>"
        + "</infNFe></NFe></nfeProc>"
    )


def chave_sintetica(n: int, dia: dt.date | None = None, cnpj: str = "33000167000101") -> str:
    dia = dia or dt.date(2026, 3, 10)
    base = f"33{dia:%y%m}{cnpj}55001{n:09d}1{n % 100000000:08d}"
    return (base + "0")[:44]


def nota_aleatoria(n: int, dia: dt.date, rnd: random.Random, taxa_erro: float = 0.02) -> NotaSint:
    """Nota sintética com ~taxa_erro de itens com desvio (para teste de carga)."""
    itens = []
    for _ in range(rnd.randint(1, 5)):
        it = ItemSint(ncm=rnd.choice(["27101921", "27101259", "27111910", "38260000", "29022000"]),
                      v_prod=round(rnd.uniform(100, 500000), 2))
        if rnd.random() < taxa_erro:
            it.v_cbs = round(it.v_prod * 0.0095, 2)
        itens.append(it)
    return NotaSint(chave=chave_sintetica(n, dia), dh_emi=f"{dia.isoformat()}T10:00:00-03:00", itens=itens)
