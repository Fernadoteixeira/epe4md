import pandas as pd
import pytest
from pathlib import Path
import epe4md
from epe4md import epe4md_casos_payback, epe4md_fatores_publicacao, epe4md_mercado_potencial, epe4md_sumariza_resultados

def test_cases_and_market_use_packaged_premises():
    cases = epe4md_casos_payback(2021, 2022)
    market = epe4md_mercado_potencial(2021)
    assert len(cases) > 0
    assert cases["nome_4md"].nunique() == 54
    assert len(market["consumidores"]) > 0
    assert market["consumidores"].isna().sum().sum() == 0

def test_summary_and_publication_labels():
    results = pd.DataFrame({"ano": [2021, 2021, 2022], "pot_mes_mw": [1000, 500, 250], "energia_mwh": [8760, 876, 438]})
    summary = epe4md_sumariza_resultados(results)
    assert summary.to_dict("records")[0]["pot_ano"] == 1.5
    assert epe4md_fatores_publicacao([{"segmento": "comercial_at_remoto"}]).iloc[0, 0] == "Comercial Remoto (AT/BT)"

def test_invalid_income_filter_is_actionable():
    with pytest.raises(ValueError, match="filtro_renda_domicilio"):
        epe4md_mercado_potencial(2021, filtro_renda_domicilio="invalido")


def test_all_public_r_functions_are_exposed():
    namespace = Path(__file__).parents[2] / "NAMESPACE"
    exported = {
        line.removeprefix("export(").removesuffix(")")
        for line in namespace.read_text(encoding="utf-8").splitlines()
        if line.startswith("export(")
    }
    assert exported == set(epe4md.__all__)
