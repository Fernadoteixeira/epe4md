from __future__ import annotations
import pandas as pd
from .data import records_to_dataframe
from .model import epe4md_fatores_publicacao, epe4md_sumariza_resultados

def _data(dados: object) -> pd.DataFrame: return records_to_dataframe(dados, "dados")
def _spec(chart_type: str, data: pd.DataFrame, x: str, y: str, color: str | None = None, **metadata: object) -> dict: return {"tipo": chart_type, "dados": data.to_dict(orient="records"), "eixo_x": x, "eixo_y": y, "cor": color, **metadata}
def epe4md_graf_geracao_ano(dados: object, ano_inicio: int = 2013, cor: str = "#953735", tamanho: int = 14) -> dict:
    frame=_data(dados); frame=frame[frame.ano>=ano_inicio]; grouped=frame.groupby(["ano","mes"],as_index=False).energia_mwh.sum(); grouped["dias_mes"] = pd.to_datetime(dict(year=grouped.ano,month=grouped.mes,day=1)).dt.days_in_month; output=grouped.groupby("ano",as_index=False).agg(dias_ano=("dias_mes","sum"),energia_mwh=("energia_mwh","sum")); output["energia_mwmed"]=output.energia_mwh/(24*output.dias_ano); return _spec("area",output,"ano","energia_mwmed",cor,tamanho=tamanho)
def epe4md_graf_geracao_mes(dados: object, ano_inicio: int = 2013, cor: str = "#953735", tamanho: int = 14) -> dict:
    frame=_data(dados); output=frame[frame.ano>=ano_inicio].groupby("data",as_index=False).energia_mwmed.sum(); return _spec("area",output,"data","energia_mwmed",cor,tamanho=tamanho)
def epe4md_graf_part_fonte_geracao(dados: object, cor: str = "#953735", tamanho: int = 14) -> dict:
    frame=_data(dados); output=frame[frame.ano==frame.ano.max()].groupby("fonte_resumo",as_index=False).energia_mwh.sum(); output["part_energia"]=output.energia_mwh/output.energia_mwh.sum(); return _spec("barra_horizontal",output,"fonte_resumo","part_energia",cor,tamanho=tamanho)
def epe4md_graf_part_fonte_potencia(dados: object, cor: str = "#112446", tamanho: int = 14) -> dict:
    output=_data(dados).groupby("fonte_resumo",as_index=False).pot_mes_mw.sum(); output["part_potencia"]=output.pot_mes_mw/output.pot_mes_mw.sum(); return _spec("barra_horizontal",output,"fonte_resumo","part_potencia",cor,tamanho=tamanho)
def epe4md_graf_part_segmento(dados: object, ano_inicio: int = 2013, tamanho: int = 14) -> dict:
    frame=epe4md_fatores_publicacao(_data(dados)); output=frame[frame.ano>=ano_inicio].groupby(["ano","segmento"],as_index=False).pot_mes_mw.sum(); output["part_potencia"]=output.pot_mes_mw/output.groupby("ano").pot_mes_mw.transform("sum"); return _spec("coluna_empilhada",output,"ano","part_potencia","segmento",tamanho=tamanho)
def epe4md_graf_pot_acum(dados: object, ano_inicio: int = 2013, cor: str = "#13475d", tamanho: int = 14) -> dict:
    return _spec("linha",epe4md_sumariza_resultados(_data(dados)).query("ano >= @ano_inicio"),"ano","pot_acum",cor,tamanho=tamanho)
def epe4md_graf_pot_anual(dados: object, ano_inicio: int = 2013, cor: str = "#13475d", tamanho: int = 14) -> dict:
    return _spec("coluna",epe4md_sumariza_resultados(_data(dados)).query("ano >= @ano_inicio"),"ano","pot_ano",cor,tamanho=tamanho)
def _accumulated(dados: object, column: str, ano_inicio: int) -> pd.DataFrame:
    frame=epe4md_fatores_publicacao(_data(dados)); output=frame.groupby(["ano",column],as_index=False).pot_mes_mw.sum().sort_values([column,"ano"]); output["pot_acum"]=output.groupby(column).pot_mes_mw.cumsum()/1000; return output[output.ano>=ano_inicio]
def epe4md_graf_pot_regiao(dados: object, ano_inicio: int = 2013, tamanho: int = 14) -> dict: return _spec("linha",_accumulated(dados,"regiao",ano_inicio),"ano","pot_acum","regiao",tamanho=tamanho)
def epe4md_graf_pot_segmento(dados: object, ano_inicio: int = 2013, tamanho: int = 14) -> dict: return _spec("linha",_accumulated(dados,"segmento",ano_inicio),"ano","pot_acum","segmento",tamanho=tamanho)
