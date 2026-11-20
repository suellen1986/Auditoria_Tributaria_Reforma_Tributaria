"""Parser de NF-e (modelo 55/65) com os grupos da Reforma Tributária.

Leiaute de referência: NT 2025.002 (grupos IBSCBS, gIBSCBS, gIBSUF, gIBSMun, gCBS,
gRed, gDif, gDevTrib, gTribRegular, gIBSCredPres/gCBSCredPres, gTribCompraGov,
gIBSCBSMono, IS e totais IBSCBSTot/ISTot).

Os campos internos de cada grupo são localizados por busca no *escopo do grupo*
(descendentes), e não por caminho fixo. Isso torna o parser tolerante às revisões
da NT que reagrupam subcampos (ex.: gIBSCBSMono em gMonoPadrao/gMonoReten/...).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from lxml import etree

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=True)


class ErroParse(ValueError):
    pass


def _f(txt: str | None) -> float | None:
    if txt is None:
        return None
    txt = txt.strip()
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return float(txt.replace(",", "."))


def _data(txt: str | None) -> dt.date | None:
    if not txt or len(txt) < 10:
        return None
    try:
        return dt.date.fromisoformat(txt[:10])
    except ValueError:
        return None


class _Ctx:
    """Ajuda a navegar com ou sem namespace."""

    __slots__ = ("ns", "_cache")

    def __init__(self, ns: str):
        self.ns = ns
        self._cache: dict[str, str] = {}

    def q(self, caminho: str) -> str:
        c = self._cache.get(caminho)
        if c is None:
            if self.ns:
                c = "/".join(f"{{{self.ns}}}{p}" for p in caminho.split("/"))
            else:
                c = caminho
            self._cache[caminho] = c
        return c

    def find(self, el, caminho: str):
        return None if el is None else el.find(self.q(caminho))

    def txt(self, el, caminho: str) -> str | None:
        if el is None:
            return None
        e = el.find(self.q(caminho))
        return e.text.strip() if e is not None and e.text else None

    def desc(self, escopo, nome: str):
        """Primeiro descendente com o nome informado (busca no escopo do grupo)."""
        if escopo is None:
            return None
        return next(escopo.iter(self.q(nome)), None)

    def dtxt(self, escopo, nome: str) -> str | None:
        e = self.desc(escopo, nome)
        return e.text.strip() if e is not None and e.text else None

    def dnum(self, escopo, nome: str) -> float | None:
        return _f(self.dtxt(escopo, nome))

    def tem(self, escopo, nome: str) -> bool:
        return self.desc(escopo, nome) is not None


def _doc(c: _Ctx, el) -> str | None:
    return c.txt(el, "CNPJ") or c.txt(el, "CPF") or c.txt(el, "idEstrangeiro")


def _grupo_tributo(c: _Ctx, g, nome_aliq: str, nome_valor: str, suf: str) -> dict[str, Any]:
    if g is None:
        return {}
    # pDif/vDif/vDevTrib/pRedAliq/pAliqEfet ficam dentro de cada gIBSUF/gIBSMun/gCBS
    return {
        f"p_{nome_valor}": c.dnum(g, nome_aliq),
        f"p_dif_{suf}": c.dnum(g, "pDif"),
        f"v_dif_{suf}": c.dnum(g, "vDif"),
        f"v_dev_trib_{suf}": c.dnum(g, "vDevTrib"),
        f"p_red_aliq_{suf}": c.dnum(g, "pRedAliq"),
        f"p_aliq_efet_{suf}": c.dnum(g, "pAliqEfet"),
        f"v_{nome_valor}": c.dnum(g, "v" + nome_aliq[1:]),
    }


_MONO = {
    "q_bc_mono": "qBCMono", "ad_rem_ibs": "adRemIBS", "ad_rem_cbs": "adRemCBS",
    "v_ibs_mono": "vIBSMono", "v_cbs_mono": "vCBSMono",
    "q_bc_mono_reten": "qBCMonoReten", "ad_rem_ibs_reten": "adRemIBSReten", "v_ibs_mono_reten": "vIBSMonoReten",
    "ad_rem_cbs_reten": "adRemCBSReten", "v_cbs_mono_reten": "vCBSMonoReten",
    "q_bc_mono_ret": "qBCMonoRet", "ad_rem_ibs_ret": "adRemIBSRet", "v_ibs_mono_ret": "vIBSMonoRet",
    "ad_rem_cbs_ret": "adRemCBSRet", "v_cbs_mono_ret": "vCBSMonoRet",
}


def _valor_imposto(c: _Ctx, imposto, grupo: str, campo: str) -> float | None:
    g = c.find(imposto, grupo)
    return c.dnum(g, campo) if g is not None else None


def parse_nfe(xml: bytes | str, chave_origem: str | None = None, fonte: str | None = None,
              hash_xml: str | None = None, lote: str | None = None) -> tuple[dict, list[dict]]:
    """Retorna (nota, itens). Lança ErroParse em XML inválido ou sem infNFe."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    try:
        raiz = etree.fromstring(xml, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise ErroParse(f"XML malformado: {e}") from e
    if raiz is None:
        raise ErroParse("XML vazio")

    ns = raiz.tag[1:].split("}", 1)[0] if isinstance(raiz.tag, str) and raiz.tag.startswith("{") else ""
    c = _Ctx(ns)
    inf = raiz if etree.QName(raiz).localname == "infNFe" else next(raiz.iter(c.q("infNFe")), None)
    if inf is None:
        raise ErroParse("Grupo infNFe não encontrado")

    chave = (inf.get("Id") or "")[3:] or chave_origem
    if not chave:
        raise ErroParse("Chave de acesso não encontrada")

    ide = c.find(inf, "ide")
    emit = c.find(inf, "emit")
    dest = c.find(inf, "dest")
    entrega = c.find(inf, "entrega")
    total = c.find(inf, "total")
    dh_emi = c.txt(ide, "dhEmi") or c.txt(ide, "dEmi")
    dt_emi = _data(dh_emi)

    cab = {
        "chave": chave,
        "fonte": fonte,
        "dt_emi": dt_emi,
        "mod": c.txt(ide, "mod"),
        "tp_nf": c.txt(ide, "tpNF"),
        "fin_nfe": c.txt(ide, "finNFe"),
        "cnpj_emit": _doc(c, emit),
        "uf_emit": c.txt(emit, "enderEmit/UF"),
        "c_mun_emit": c.txt(emit, "enderEmit/cMun"),
        "cnpj_dest": _doc(c, dest),
        "uf_dest": c.txt(dest, "enderDest/UF"),
        "c_mun_dest": c.txt(dest, "enderDest/cMun"),
        "uf_entrega": c.txt(entrega, "UF"),
        "c_mun_entrega": c.txt(entrega, "cMun"),
        "c_mun_fg": c.txt(ide, "cMunFG"),
        "c_mun_fg_ibs": c.txt(ide, "cMunFGIBS"),
        "hash_xml": hash_xml,
        "lote": lote,
    }

    itens: list[dict] = []
    for det in inf.iterfind(c.q("det")):
        prod = c.find(det, "prod")
        imp = c.find(det, "imposto")
        item: dict[str, Any] = dict(cab)
        item.update({
            "n_item": int(det.get("nItem") or len(itens) + 1),
            "c_prod": c.txt(prod, "cProd"),
            "x_prod": c.txt(prod, "xProd"),
            "ncm": c.txt(prod, "NCM"),
            "cest": c.txt(prod, "CEST"),
            "cfop": c.txt(prod, "CFOP"),
            "u_com": c.txt(prod, "uCom"),
            "q_com": _f(c.txt(prod, "qCom")),
            "u_trib": c.txt(prod, "uTrib"),
            "q_trib": _f(c.txt(prod, "qTrib")),
            "v_prod": _f(c.txt(prod, "vProd")),
            "v_frete": _f(c.txt(prod, "vFrete")),
            "v_seg": _f(c.txt(prod, "vSeg")),
            "v_desc": _f(c.txt(prod, "vDesc")),
            "v_outro": _f(c.txt(prod, "vOutro")),
            "v_icms": _valor_imposto(c, imp, "ICMS", "vICMS"),
            "v_icms_st": _valor_imposto(c, imp, "ICMS", "vICMSST"),
            "v_ipi": _valor_imposto(c, imp, "IPI", "vIPI"),
            "v_pis": _valor_imposto(c, imp, "PIS", "vPIS"),
            "v_cofins": _valor_imposto(c, imp, "COFINS", "vCOFINS"),
        })

        ibscbs = c.find(imp, "IBSCBS")
        item["ibscbs_presente"] = ibscbs is not None
        if ibscbs is not None:
            g = c.find(ibscbs, "gIBSCBS")
            item["cst"] = c.txt(ibscbs, "CST")
            item["cclasstrib"] = c.txt(ibscbs, "cClassTrib")
            item["v_bc"] = _f(c.txt(g, "vBC"))
            item.update(_grupo_tributo(c, c.find(g, "gIBSUF"), "pIBSUF", "ibs_uf", "uf"))
            item.update(_grupo_tributo(c, c.find(g, "gIBSMun"), "pIBSMun", "ibs_mun", "mun"))
            item["v_ibs"] = _f(c.txt(g, "vIBS"))
            item.update(_grupo_tributo(c, c.find(g, "gCBS"), "pCBS", "cbs", "cbs"))
            mono = c.find(ibscbs, "gIBSCBSMono")
            item.update({
                "tem_g_red": c.tem(g, "gRed"),
                "tem_g_dif": c.tem(g, "gDif"),
                "tem_g_dev_trib": c.tem(g, "gDevTrib"),
                "tem_g_trib_regular": c.tem(g, "gTribRegular"),
                "tem_g_cred_pres": c.tem(g, "gIBSCredPres") or c.tem(g, "gCBSCredPres"),
                "tem_g_trib_compra_gov": c.tem(g, "gTribCompraGov"),
                "tem_mono": mono is not None,
            })
            if mono is not None:
                for campo, tag in _MONO.items():
                    item[campo] = c.dnum(mono, tag)

        is_ = c.find(imp, "IS")
        item["is_presente"] = is_ is not None
        if is_ is not None:
            item.update({
                "cst_is": c.dtxt(is_, "CSTIS"),
                "cclasstrib_is": c.dtxt(is_, "cClassTribIS"),
                "v_bc_is": c.dnum(is_, "vBCIS"),
                "p_is": c.dnum(is_, "pIS"),
                "p_is_espec": c.dnum(is_, "pISEspec"),
                "u_trib_is": c.dtxt(is_, "uTrib"),
                "q_trib_is": c.dnum(is_, "qTrib"),
                "v_is": c.dnum(is_, "vIS"),
            })
        itens.append(item)

    tot = c.find(total, "IBSCBSTot")
    gibs = c.find(tot, "gIBS")
    gcbs = c.find(tot, "gCBS")
    gmono = c.find(tot, "gMono")
    nota = {
        "chave": chave,
        "fonte": fonte,
        "versao_leiaute": inf.get("versao"),
        "mod": cab["mod"],
        "serie": c.txt(ide, "serie"),
        "n_nf": c.txt(ide, "nNF"),
        "tp_nf": cab["tp_nf"],
        "fin_nfe": cab["fin_nfe"],
        "dh_emi": dh_emi,
        "dt_emi": dt_emi,
        "cnpj_emit": cab["cnpj_emit"],
        "x_nome_emit": c.txt(emit, "xNome"),
        "uf_emit": cab["uf_emit"],
        "cnpj_dest": cab["cnpj_dest"],
        "x_nome_dest": c.txt(dest, "xNome"),
        "uf_dest": cab["uf_dest"],
        "qtd_itens": len(itens),
        "v_nf": _f(c.txt(total, "ICMSTot/vNF")),
        "tot_presente": tot is not None,
        "tot_v_bc_ibscbs": _f(c.txt(tot, "vBCIBSCBS")),
        "tot_v_ibs_uf": _f(c.txt(gibs, "gIBSUF/vIBSUF")),
        "tot_v_ibs_mun": _f(c.txt(gibs, "gIBSMun/vIBSMun")),
        "tot_v_ibs": _f(c.txt(gibs, "vIBS")),
        "tot_v_cbs": _f(c.txt(gcbs, "vCBS")),
        "tot_v_ibs_mono": c.dnum(gmono, "vIBSMono"),
        "tot_v_cbs_mono": c.dnum(gmono, "vCBSMono"),
        "tot_v_is": _f(c.txt(total, "ISTot/vIS")),
        "hash_xml": hash_xml,
        "lote": lote,
    }
    return nota, itens
