from __future__ import annotations

from calendar import monthrange
from datetime import date
from math import exp
from typing import Any
import numpy as np
import pandas as pd

from .data import load_workbook, records_to_dataframe, require_columns

SEGMENTOS = {"comercial_at", "comercial_at_remoto", "comercial_bt", "residencial", "residencial_remoto"}
RENDAS = {"total", "maior_1sm", "maior_2sm", "maior_3sm", "maior_5sm"}


def _directory(directory: str | None) -> str | None:
    return directory


def _validate_year(ano_base: int, ano_max_resultado: int = 2050) -> None:
    if not isinstance(ano_base, (int, np.integer)):
        raise TypeError("ano_base deve ser um número inteiro.")
    if ano_max_resultado > 2050:
        raise ValueError("ano_max_resultado deve ser menor ou igual a 2050.")
    if ano_max_resultado < 2013:
        raise ValueError("ano_max_resultado deve ser maior ou igual a 2013.")


def _fill_regulatory_premises(premissas_reg: pd.DataFrame) -> pd.DataFrame:
    required = ["ano", "alternativa", "p_transicao", "binomia", "demanda_g"]
    require_columns(premissas_reg, required, "premissas_reg")
    if not pd.api.types.is_numeric_dtype(premissas_reg["ano"]):
        raise TypeError("premissas_reg.ano deve ser numérica.")
    for column in ["alternativa", "p_transicao"]:
        if not pd.api.types.is_numeric_dtype(premissas_reg[column]):
            raise TypeError(f"premissas_reg.{column} deve ser numérica.")
    if not pd.api.types.is_bool_dtype(premissas_reg["binomia"]):
        raise TypeError("premissas_reg.binomia deve ser booleana.")
    if not pd.api.types.is_bool_dtype(premissas_reg["demanda_g"]):
        raise TypeError("premissas_reg.demanda_g deve ser booleana.")
    years = pd.DataFrame({"ano": range(2013, 2051)})
    filled = years.merge(premissas_reg, on="ano", how="left").ffill()
    filled["p_transicao"] = filled["p_transicao"].fillna(1.0)
    filled["alternativa"] = filled["alternativa"].fillna(0).astype(int)
    filled[["binomia", "demanda_g"]] = filled[["binomia", "demanda_g"]].fillna(False).astype(bool)
    filled.loc[filled["binomia"] & filled["alternativa"].isin([0, 1]), "alternativa"] = 2
    return filled


def epe4md_casos_payback(ano_base: int, ano_max_resultado: int = 2050,
                          inflacao: float = 0.0375, ano_troca_inversor: int = 11,
                          fator_custo_inversor: float = 0.15,
                          dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base, ano_max_resultado)
    if ano_troca_inversor < 1:
        raise ValueError("ano_troca_inversor deve ser maior ou igual a 1.")
    potencia = load_workbook(ano_base, "potencia_tipica.xlsx", dir_dados_premissas)
    fatores = load_workbook(ano_base, "fc_distribuidoras.xlsx", dir_dados_premissas)
    injecao = load_workbook(ano_base, "injecao.xlsx", dir_dados_premissas)
    custos = load_workbook(ano_base, "custos.xlsx", dir_dados_premissas, "custos")
    injecao = injecao[injecao["fonte_resumo"] == "Fotovoltaica"].copy()
    injecao["oem_anual"] = np.where(injecao["segmento"] == "comercial_at_remoto", .02, .01)
    cases = injecao.merge(fatores, how="cross").merge(potencia, on="segmento", how="left")
    cases["fc"] = np.where(cases["segmento"] == "comercial_at_remoto", cases["fc_remoto"], cases["fc_local"])
    cases["vida_util"] = 25
    cases["degradacao"] = .005
    cases["geracao_1_kwh"] = cases["pot_sistemas"] * cases["fc"] * 8760
    costs = custos.copy()
    costs["custo_inversor"] = fator_custo_inversor * costs["custo_unitario"]
    cases = cases.merge(costs, on="segmento", how="inner")
    cases["capex_inicial"] = cases["custo_unitario"] * cases["pot_sistemas"] * 1000
    cases["capex_inversor"] = cases["custo_inversor"] * cases["pot_sistemas"] * 1000 * (1 + inflacao) ** (ano_troca_inversor - 1)
    cases = cases[cases["ano"] <= ano_max_resultado].sort_values(["nome_4md", "segmento", "ano"])
    return cases.reset_index(drop=True)


def _taxa_interna_retorno(cashflows: list[float]) -> float:
    # Bisection is deterministic and avoids a dependency on a finance package.
    def value(rate: float) -> float:
        return sum(amount / (1 + rate) ** index for index, amount in enumerate(cashflows))
    lower, upper = -0.9999, 10.0
    if value(lower) * value(upper) > 0:
        return float("nan")
    for _ in range(100):
        middle = (lower + upper) / 2
        if value(lower) * value(middle) <= 0:
            upper = middle
        else:
            lower = middle
    return (lower + upper) / 2


def _payback_metric(cashflows: list[float]) -> float:
    accumulated = np.cumsum(cashflows)
    negative = np.flatnonzero(accumulated < 0)
    if len(negative) == len(accumulated):
        return float(len(accumulated))
    if not len(negative):
        return 0.0
    index = int(negative[-1])
    return index + 1 + (-accumulated[index] / (accumulated[index + 1] - accumulated[index]))


def epe4md_payback(casos_payback: pd.DataFrame | list[dict[str, Any]], premissas_reg: pd.DataFrame | list[dict[str, Any]],
                    ano_base: int, sequencial: bool = True, filtro_de_uf: str = "N",
                    filtro_de_segmento: str = "N", filtro_de_custo_unitario_max: float | None = None,
                    altera_sistemas_existentes: bool = True, ano_decisao_alteracao: int = 2023,
                    inflacao: float = .0375, taxa_desconto_nominal: float = .13,
                    custo_reforco_rede: float = 200, ano_troca_inversor: int = 11,
                    pagamento_disponibilidade: float = .3, disponibilidade_kwh_mes: float = 100,
                    desconto_capex_local: float = 0, anos_desconto: int | list[int] = 0,
                    dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base)
    cases = records_to_dataframe(casos_payback, "casos_payback")
    require_columns(cases, ["nome_4md", "ano", "segmento", "vida_util", "fator_autoconsumo", "geracao_1_kwh", "degradacao", "capex_inicial", "capex_inversor", "oem_anual", "pot_sistemas", "custo_unitario"], "casos_payback")
    regulatory = _fill_regulatory_premises(records_to_dataframe(premissas_reg, "premissas_reg"))
    construction = load_workbook(ano_base, "tempo_construcao.xlsx", dir_dados_premissas, "fator")
    tariffs = load_workbook(ano_base, "tarifas_4md.xlsx", dir_dados_premissas)
    regions = load_workbook(ano_base, "tabela_dist_subs.xlsx", dir_dados_premissas)
    tariffs_a = tariffs[tariffs["subgrupo"] == "A4"].copy()
    demand = tariffs_a[["nome_4md", "ano", "tarifa_demanda_c", "tarifa_demanda_g"]].drop_duplicates()
    tariff_parts = [
        tariffs_a.assign(segmento="comercial_at", tarifa_demanda_c=0, tarifa_demanda_g=0),
        tariffs[tariffs["subgrupo"] == "B3"].drop(columns=["tarifa_demanda_c", "tarifa_demanda_g"]).assign(segmento="comercial_at_remoto").merge(demand, on=["nome_4md", "ano"]),
        tariffs[tariffs["subgrupo"] == "B1"].assign(segmento="residencial"),
        tariffs[tariffs["subgrupo"] == "B1"].assign(segmento="residencial_remoto"),
        tariffs[tariffs["subgrupo"] == "B3"].assign(segmento="comercial_bt"),
    ]
    all_tariffs = pd.concat(tariff_parts, ignore_index=True)
    cases = cases.merge(regions, on="nome_4md", how="left")
    if filtro_de_uf != "N" and filtro_de_uf in set(cases["uf"].dropna()): cases = cases[cases["uf"] == filtro_de_uf]
    if filtro_de_segmento != "N" and filtro_de_segmento in SEGMENTOS: cases = cases[cases["segmento"] == filtro_de_segmento]
    if filtro_de_custo_unitario_max is not None: cases = cases[cases["custo_unitario"] <= filtro_de_custo_unitario_max]
    discounted_years = {anos_desconto} if isinstance(anos_desconto, int) else set(anos_desconto)
    rows: list[dict[str, Any]] = []
    construction_factors = construction.set_index("segmento")["fator_construcao"].to_dict()
    regulatory_by_year = regulatory.set_index("ano").to_dict("index")
    tariff_index = all_tariffs.set_index(["ano", "nome_4md", "segmento", "alternativa"])
    for _, case in cases.iterrows():
        annual: list[float] = []
        for simulation_year in range(1, int(case["vida_util"]) + 1):
            tariff_year = min(int(case["ano"] + simulation_year - 1), 2050) if altera_sistemas_existentes and case["ano"] >= ano_decisao_alteracao else int(case["ano"])
            premise = regulatory_by_year[tariff_year]
            try:
                tariff = tariff_index.loc[(tariff_year, case["nome_4md"], case["segmento"], premise["alternativa"])]
            except KeyError as error:
                raise ValueError(f"Tarifa ausente para {case['nome_4md']}, ano {tariff_year}, segmento {case['segmento']}.") from error
            if isinstance(tariff, pd.DataFrame): tariff = tariff.iloc[0]
            construction_factor = construction_factors.get(case["segmento"], 1) if simulation_year == 1 else 1
            inflation_factor = (1 + inflacao) ** (simulation_year - 1)
            energy = case["geracao_1_kwh"] * construction_factor * (1 + case["degradacao"]) ** (1 - simulation_year)
            autoconsumed, injected = energy * case["fator_autoconsumo"], energy * (1 - case["fator_autoconsumo"])
            tariff_autoconsumo = tariff["tarifa_autoc_bin_tusd"] if premise["binomia"] else tariff["tarifa_autoc_tusd"]
            tariff_demand = tariff["tarifa_demanda_g"] if premise["demanda_g"] else tariff["tarifa_demanda_c"]
            revenue_autoconsumo = inflation_factor * autoconsumed * (tariff_autoconsumo + tariff["tarifa_autoc_te"]) / (1 - tariff["impostos_cheio"])
            revenue_injecao = inflation_factor * injected * (tariff["tarifa_inj_te"] / (1 - tariff["impostos_cheio"]) + tariff["tarifa_inj_tusd"] / (1 - tariff["impostos_tusd"]))
            payment = -premise["p_transicao"] * inflation_factor * injected * (tariff["pag_inj_te"] / (1 - tariff["impostos_cheio"]) + tariff["pag_inj_tusd"] / (1 - tariff["impostos_tusd"]))
            demand_cost = -inflation_factor * case["pot_sistemas"] * tariff_demand * 12 / (1 - tariff["impostos_cheio"])
            availability = 0 if case["segmento"] == "comercial_at" or premise["binomia"] or case["ano"] + simulation_year - 1 > 2022 else -pagamento_disponibilidade * 12 * disponibilidade_kwh_mes * construction_factor * inflation_factor * (tariff_autoconsumo + tariff["tarifa_autoc_te"]) / (1 - tariff["impostos_cheio"])
            capex = -case["capex_inicial"] if simulation_year == 1 else 0
            if case["segmento"] in {"residencial", "comercial_bt", "comercial_at"} and int(case["ano"]) in discounted_years: capex *= 1 - desconto_capex_local
            inverter = -case["capex_inversor"] if simulation_year == ano_troca_inversor else 0
            reinforcement = -custo_reforco_rede * case["pot_sistemas"] if case["segmento"] == "comercial_at_remoto" and simulation_year == 1 else 0
            annual.append(capex + inverter + reinforcement + revenue_autoconsumo + revenue_injecao + payment + demand_cost - case["oem_anual"] * case["capex_inicial"] * construction_factor + availability)
        nominal = _taxa_interna_retorno(annual)
        payback = _payback_metric(annual)
        discounted = [amount / (1 + taxa_desconto_nominal) ** index for index, amount in enumerate(annual)]
        rows.append({**case.to_dict(), "payback": payback, "payback_desc": _payback_metric(discounted), "tir_nominal": -.2 if np.isnan(nominal) and payback == 25 else nominal, "tir_real": (1 + nominal) / (1 + inflacao) - 1 if not np.isnan(nominal) else np.nan})
    return pd.DataFrame(rows)


def epe4md_mercado_potencial(ano_base: int, filtro_renda_domicilio: str = "maior_3sm", filtro_comercial: float | None = None,
                              tx_cresc_grupo_a: float = .016, dir_dados_premissas: str | None = None) -> dict[str, pd.DataFrame]:
    _validate_year(ano_base)
    if filtro_renda_domicilio not in RENDAS: raise ValueError(f"filtro_renda_domicilio deve ser um destes valores: {', '.join(sorted(RENDAS))}.")
    total = load_workbook(ano_base, "total_domicilios.xlsx", dir_dados_premissas)
    growth = load_workbook(ano_base, "crescimento_mercado.xlsx", dir_dados_premissas).sort_values("ano")
    growth["crescimento_acumulado"] = (1 + growth["taxa_crescimento_mercado"]).cumprod()
    income = load_workbook(ano_base, "consumidores_residenciais_renda.xlsx", dir_dados_premissas)
    income["maior_5sm"] = income[["domicilios_5a10sm", "domicilios_10a15sm", "domicilios_15a20sm", "domicilios_maior20sm"]].sum(axis=1)
    income["maior_3sm"] = income["maior_5sm"] + income["domicilios_3a5sm"]
    income["maior_2sm"] = income["maior_3sm"] + income["domicilios_2a3sm"]
    income["maior_1sm"] = income["maior_2sm"] + income["domicilios_1a2sm"]
    income["total"] = income["domicilios_pp"]
    incomes = income.melt(id_vars="nome_4md", value_vars=sorted(RENDAS), var_name="renda", value_name="domicilios")
    years = pd.DataFrame({"ano": range(2013, 2051)})
    residential = incomes.merge(years, how="cross").merge(growth[["ano", "crescimento_acumulado"]], on="ano", how="left")
    residential["consumidores_proj"] = (residential["domicilios"] * residential["crescimento_acumulado"]).round()
    def market_customers(filename: str, annual_growth: float | None = None) -> pd.DataFrame:
        raw = load_workbook(ano_base, filename, dir_dados_premissas).drop(columns="empresa")
        observed = raw.melt(id_vars="nome_4md", var_name="ano", value_name="consumidores")
        observed["ano"] = observed["ano"].astype(int)
        all_years = observed[["nome_4md"]].drop_duplicates().merge(years, how="cross").merge(observed, on=["nome_4md", "ano"], how="left").sort_values(["nome_4md", "ano"])
        all_years["consumidores"] = all_years.groupby("nome_4md")["consumidores"].ffill()
        if annual_growth is None:
            last_year = int(observed["ano"].max())
            future_growth = growth[growth["ano"] > last_year][["ano", "crescimento_acumulado"]]
            all_years = all_years.merge(future_growth, on="ano", how="left")
            all_years["consumidores_proj"] = np.where(all_years["crescimento_acumulado"].notna(), (all_years["consumidores"] * all_years["crescimento_acumulado"]).round(), all_years["consumidores"])
        else:
            all_years["steps"] = all_years.groupby("nome_4md")["consumidores"].transform(lambda values: values.isna().cumsum())
            all_years["consumidores_proj"] = (all_years["consumidores"] * (1 + annual_growth) ** all_years["steps"]).round()
        return all_years[["nome_4md", "ano", "consumidores_proj"]]
    commercial = market_customers("consumidores_b2b3.xlsx")
    high_voltage = market_customers("consumidores_a.xlsx", tx_cresc_grupo_a)
    technical = load_workbook(ano_base, "fator_tecnico.xlsx", dir_dados_premissas)[["nome_4md", "fator_tecnico"]]
    income_selected = residential[residential["renda"] == filtro_renda_domicilio].merge(technical, on="nome_4md")
    niche_factor = income_selected.groupby("ano", as_index=False)["consumidores_proj"].sum().merge(total, on="ano")
    niche_factor["fator_nicho_comercial"] = niche_factor["consumidores_proj"] / niche_factor["domicilios"]
    if filtro_comercial is not None: niche_factor["fator_nicho_comercial"] = filtro_comercial
    residential_parts = income_selected.assign(residencial=lambda value: (value.consumidores_proj * value.fator_tecnico).round(), residencial_remoto=lambda value: (value.consumidores_proj * (1 - value.fator_tecnico)).round()).melt(id_vars=["nome_4md", "ano"], value_vars=["residencial", "residencial_remoto"], var_name="segmento", value_name="consumidores")
    commercial_parts = commercial.merge(technical, on="nome_4md").merge(niche_factor[["ano", "fator_nicho_comercial"]], on="ano").assign(comercial_bt=lambda value: (value.consumidores_proj * value.fator_tecnico * value.fator_nicho_comercial).round(), comercial_at_remoto=lambda value: (value.consumidores_proj * (1 - value.fator_tecnico) * value.fator_nicho_comercial).round()).melt(id_vars=["nome_4md", "ano"], value_vars=["comercial_bt", "comercial_at_remoto"], var_name="segmento", value_name="consumidores")
    high_voltage = high_voltage.assign(segmento="comercial_at", consumidores=lambda value: value.consumidores_proj)[["nome_4md", "ano", "segmento", "consumidores"]]
    consumers = pd.concat([residential_parts, commercial_parts, high_voltage], ignore_index=True)
    totals = pd.concat([total.assign(segmento="residencial", total_ucs=total["domicilios"])[["ano", "segmento", "total_ucs"]], commercial.groupby("ano", as_index=False)["consumidores_proj"].sum().assign(segmento="comercial_bt", total_ucs=lambda value: value.consumidores_proj)[["ano", "segmento", "total_ucs"]], high_voltage.groupby("ano", as_index=False)["consumidores"].sum().assign(segmento="comercial_at", total_ucs=lambda value: value.consumidores)[["ano", "segmento", "total_ucs"]]], ignore_index=True)
    return {"consumidores": consumers.reset_index(drop=True), "consumidores_totais": totals.reset_index(drop=True)}


def _bass_fraction(p: float, q: float, time: pd.Series | np.ndarray) -> np.ndarray:
    exponent = np.exp(-(p + q) * np.asarray(time, dtype=float))
    return (1 - exponent) / (1 + (q / p) * exponent)


def _fit_bass(case: pd.DataFrame, spb: float, p_max: float, q_max: float) -> tuple[float, float]:
    if case.empty: return .0001, .01
    times = case["ano"].to_numpy(dtype=float) - 2012
    market = np.exp(-spb * case["payback"].to_numpy(dtype=float)) * case["consumidores"].to_numpy(dtype=float)
    actual = case["adotantes_acum"].to_numpy(dtype=float)
    p_lower, q_lower = .0001, .01
    best_p, best_q = min(.005, p_max), min(.3, q_max)
    step_p, step_q = max((p_max - p_lower) / 4, .0001), max((q_max - q_lower) / 4, .01)
    def error(p: float, q: float) -> float: return float(np.square(actual - _bass_fraction(p, q, times) * market).sum())
    best_error = error(best_p, best_q)
    for _ in range(12):
        candidates = [(max(p_lower, min(p_max, best_p + delta_p * step_p)), max(q_lower, min(q_max, best_q + delta_q * step_q))) for delta_p in (-1, 0, 1) for delta_q in (-1, 0, 1)]
        best_p, best_q = min(candidates, key=lambda candidate: error(*candidate))
        best_error = error(best_p, best_q)
        step_p /= 2
        step_q /= 2
    return best_p, best_q


def epe4md_calibra_curva_s(resultado_payback: pd.DataFrame | list[dict[str, Any]], consumidores: dict[str, Any], ano_base: int,
                           ano_max_resultado: int = 2050, spb: float = .3, p_max: float = .01,
                           q_max: float = 1, dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base, ano_max_resultado)
    results = records_to_dataframe(resultado_payback, "resultado_payback")
    consumer_data = records_to_dataframe(consumidores.get("consumidores"), "consumidores.consumidores")
    history = load_workbook(ano_base, "base_mmgd.xlsx", dir_dados_premissas)
    history = history[history["ano"] <= ano_base].groupby(["nome_4md", "segmento", "ano"], as_index=False)["qtde_u_csrecebem_os_creditos"].sum().rename(columns={"qtde_u_csrecebem_os_creditos": "adotantes_hist"})
    historical = results[results["ano"] <= ano_base][["nome_4md", "segmento", "ano", "payback", "payback_desc"]].copy()
    historical["payback"] = np.where(historical["segmento"].isin(["residencial", "residencial_remoto"]), historical["payback"], historical["payback_desc"])
    calibration = historical.merge(consumer_data, on=["nome_4md", "segmento", "ano"], how="left").merge(history, on=["nome_4md", "segmento", "ano"], how="left")
    calibration["adotantes_hist"] = calibration["adotantes_hist"].fillna(0)
    calibration = calibration.sort_values("ano")
    calibration["adotantes_acum"] = calibration.groupby(["nome_4md", "segmento"])["adotantes_hist"].cumsum()
    parameters = []
    for keys, case in calibration.groupby(["nome_4md", "segmento"]):
        if case["consumidores"].isna().any():
            raise ValueError(f"Mercado potencial ausente para {keys[0]}, segmento {keys[1]}.")
        p, q = _fit_bass(case, spb, p_max, q_max)
        parameters.append({"nome_4md": keys[0], "segmento": keys[1], "p": p, "q": q, "spb": spb})
    years = pd.DataFrame({"ano": range(2013, min(ano_max_resultado, 2050) + 1)})
    optimized = pd.DataFrame(parameters).merge(years, how="cross")
    optimized["Ft"] = _bass_fraction(optimized["p"], optimized["q"], optimized["ano"] - 2012)
    optimized = optimized.merge(consumer_data, on=["nome_4md", "segmento", "ano"], how="left").merge(historical[["nome_4md", "segmento", "ano", "payback"]], on=["nome_4md", "segmento", "ano"], how="left")
    if optimized[["consumidores", "payback"]].isna().any().any():
        raise ValueError("Dados de consumidores ou payback ausentes na curva de difusão.")
    optimized["mercado_potencial"] = (np.exp(-spb * optimized["payback"]) * optimized["consumidores"]).round().clip(lower=1)
    return optimized


def epe4md_proj_adotantes(casos_otimizados: pd.DataFrame | list[dict[str, Any]], consumidores: dict[str, Any], ano_base: int,
                           dir_dados_premissas: str | None = None) -> dict[str, pd.DataFrame]:
    optimized = records_to_dataframe(casos_otimizados, "casos_otimizados").sort_values(["nome_4md", "segmento", "ano"])
    consumer_data = records_to_dataframe(consumidores.get("consumidores"), "consumidores.consumidores")
    total_consumers = records_to_dataframe(consumidores.get("consumidores_totais"), "consumidores.consumidores_totais")
    history = load_workbook(ano_base, "base_mmgd.xlsx", dir_dados_premissas)
    projected = optimized.copy()
    projected["adotantes_acum"] = projected["mercado_potencial"] * projected["Ft"]
    projected["adotantes_ano"] = projected.groupby(["nome_4md", "segmento"])["adotantes_acum"].diff().fillna(projected["adotantes_acum"]).clip(lower=0).round()
    # The R implementation smooths zero-adopter years with the next two-year average.
    projected["smooth"] = projected.groupby(["nome_4md", "segmento"])["adotantes_ano"].transform(lambda values: values.rolling(2, min_periods=1).mean().shift(-1).fillna(values))
    prior_zero = projected.groupby(["nome_4md", "segmento"])["adotantes_ano"].shift(1).eq(0)
    projected.loc[((projected["adotantes_ano"] == 0) | prior_zero) & (projected["ano"] > 2019), "adotantes_ano"] = projected.loc[((projected["adotantes_ano"] == 0) | prior_zero) & (projected["ano"] > 2019), "smooth"].round()
    projected["adotantes_acum"] = projected.groupby(["nome_4md", "segmento"])["adotantes_ano"].cumsum()
    shares = history.groupby(["nome_4md", "segmento", "fonte_resumo"], as_index=False)["qtde_u_csrecebem_os_creditos"].sum()
    shares["part_fonte"] = shares["qtde_u_csrecebem_os_creditos"] / shares.groupby(["nome_4md", "segmento"])["qtde_u_csrecebem_os_creditos"].transform("sum")
    historical = history[history["ano"] <= ano_base].groupby(["ano", "nome_4md", "segmento", "fonte_resumo"], as_index=False)["qtde_u_csrecebem_os_creditos"].sum().rename(columns={"qtde_u_csrecebem_os_creditos": "adotantes_hist"})
    projected = projected.merge(shares[["nome_4md", "segmento", "fonte_resumo", "part_fonte"]], on=["nome_4md", "segmento"], how="left").merge(historical, on=["ano", "nome_4md", "segmento", "fonte_resumo"], how="left")
    projected["part_fonte"] = projected["part_fonte"].fillna(
        pd.Series(np.where(projected["fonte_resumo"].eq("Fotovoltaica"), 1, 0), index=projected.index)
    )
    projected["adotantes_ano"] = (projected["adotantes_ano"] * projected["part_fonte"]).round()
    projected.loc[projected["ano"] <= ano_base, "adotantes_ano"] = projected.loc[projected["ano"] <= ano_base, "adotantes_hist"].fillna(0)
    projected["adotantes_acum"] = projected.groupby(["nome_4md", "segmento", "fonte_resumo"])["adotantes_ano"].cumsum()
    projected["mercado_potencial"] /= 4
    adoption = projected.assign(segmento_agregado=projected["segmento"].replace({"residencial_remoto": "residencial", "comercial_at_remoto": "comercial_bt"})).groupby(["ano", "segmento_agregado"], as_index=False).agg(adotantes=("adotantes_acum", "sum"), mercado_potencial=("mercado_potencial", "sum")).rename(columns={"segmento_agregado": "segmento"})
    niche = consumer_data.assign(segmento_agregado=consumer_data["segmento"].replace({"residencial_remoto": "residencial", "comercial_at_remoto": "comercial_bt"})).groupby(["ano", "segmento_agregado"], as_index=False)["consumidores"].sum().rename(columns={"segmento_agregado": "segmento", "consumidores": "mercado_nicho"})
    participation = adoption.merge(total_consumers, on=["ano", "segmento"], how="left").merge(niche, on=["ano", "segmento"], how="left")
    participation["penetracao_total"] = participation["adotantes"] / participation["total_ucs"]
    participation["penetracao_nicho"] = participation["adotantes"] / participation["mercado_nicho"]
    participation["penetracao_potencial"] = participation["adotantes"] / participation["mercado_potencial"]
    return {"proj_adotantes": projected.drop(columns="smooth"), "part_adotantes": participation}


def epe4md_proj_potencia(lista_adotantes: dict[str, Any], ano_base: int, dir_dados_premissas: str | None = None) -> dict[str, pd.DataFrame]:
    projected = records_to_dataframe(lista_adotantes.get("proj_adotantes"), "lista_adotantes.proj_adotantes")
    history = load_workbook(ano_base, "base_mmgd.xlsx", dir_dados_premissas)
    typical = load_workbook(ano_base, "potencia_tipica.xlsx", dir_dados_premissas)
    means = history.groupby(["nome_4md", "segmento", "fonte_resumo"], as_index=False).agg(pot_total=("potencia_instalada_k_w", "sum"), adotantes_total=("qtde_u_csrecebem_os_creditos", "sum"))
    means["pot_media"] = means["pot_total"] / means["adotantes_total"]
    means = means.merge(typical, on="segmento", how="left")
    means["pot_media"] = means["pot_media"].fillna(means["pot_sistemas"])
    output = projected.merge(means[["nome_4md", "segmento", "fonte_resumo", "pot_media"]], on=["nome_4md", "segmento", "fonte_resumo"], how="left")
    historical = history[history["ano"] <= ano_base].groupby(["ano", "nome_4md", "segmento", "fonte_resumo"], as_index=False)["potencia_instalada_k_w"].sum().rename(columns={"potencia_instalada_k_w": "pot_hist"})
    output["pot_ano"] = output["adotantes_ano"] * output["pot_media"]
    output = output.merge(historical, on=["ano", "nome_4md", "segmento", "fonte_resumo"], how="left")
    output.loc[output["ano"] <= ano_base, "pot_ano"] = output.loc[output["ano"] <= ano_base, "pot_hist"].fillna(0)
    output["pot_ano_mw"] = output["pot_ano"] / 1000
    output = output.sort_values(["nome_4md", "segmento", "fonte_resumo", "ano"])
    output["pot_acum_mw"] = output.groupby(["nome_4md", "segmento", "fonte_resumo"])["pot_ano_mw"].cumsum()
    return {"proj_potencia": output, "part_adotantes": records_to_dataframe(lista_adotantes.get("part_adotantes"), "lista_adotantes.part_adotantes")}


def epe4md_proj_mensal(lista_potencia: dict[str, Any], ano_base: int, filtro_nome4md: str = "N", filtro_de_segmento: str = "N",
                        ano_max_resultado: int = 2050, ajuste_ano_corrente: bool = False, ultimo_mes_ajuste: int | None = None,
                        metodo_ajuste: str | None = None, dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base, ano_max_resultado)
    if ajuste_ano_corrente and (ultimo_mes_ajuste is None or ultimo_mes_ajuste not in range(1, 13) or metodo_ajuste not in {"extrapola", "substitui"}):
        raise ValueError("ajuste_ano_corrente requer ultimo_mes_ajuste entre 1 e 12 e metodo_ajuste 'extrapola' ou 'substitui'.")
    annual = records_to_dataframe(lista_potencia.get("proj_potencia"), "lista_potencia.proj_potencia")
    history = load_workbook(ano_base, "base_mmgd.xlsx", dir_dados_premissas)
    history["data_conexao"] = pd.to_datetime(history["data_conexao"])
    history["mes"] = history["data_conexao"].dt.month
    monthly_totals = history[(history["ano"] >= 2014) & (history["ano"] <= ano_base)].groupby("mes")["potencia_mw"].sum()
    factors = monthly_totals / monthly_totals.mean()
    factors = factors.reindex(range(1, 13), fill_value=1.0)
    annual = annual[annual["ano"] <= ano_max_resultado]
    future = annual[annual["ano"] > ano_base].copy()
    future = future.merge(pd.DataFrame({"mes": range(1, 13)}), how="cross")
    future["data_conexao"] = pd.to_datetime(dict(year=future["ano"], month=future["mes"], day=1))
    future["pot_mes_mw"] = future["pot_ano_mw"] * future["mes"].map(factors) / 12
    future["adotantes_mes"] = (future["adotantes_ano"] * future["mes"].map(factors) / 12).round()
    historical = history[history["ano"] <= ano_base].rename(
        columns={"potencia_mw": "pot_mes_mw", "qtde_u_csrecebem_os_creditos": "adotantes_mes"}
    )
    historical = historical[["data_conexao", "ano", "mes", "nome_4md", "fonte_resumo", "segmento", "pot_mes_mw", "adotantes_mes"]]
    if ajuste_ano_corrente:
        cutoff = pd.Timestamp(ano_base + 1, ultimo_mes_ajuste, 1)
        observed = history[history["data_conexao"] <= cutoff].copy()
        historical = observed.rename(columns={"potencia_mw": "pot_mes_mw", "qtde_u_csrecebem_os_creditos": "adotantes_mes"})[["data_conexao", "ano", "mes", "nome_4md", "fonte_resumo", "segmento", "pot_mes_mw", "adotantes_mes"]]
        if metodo_ajuste == "substitui": future = future[future["data_conexao"] > cutoff]
        else: future = future[future["ano"] > ano_base + 1]
    output = pd.concat([historical, future[["data_conexao", "ano", "mes", "nome_4md", "fonte_resumo", "segmento", "pot_mes_mw", "adotantes_mes"]]], ignore_index=True)
    factors_pq = annual[["ano", "segmento", "fonte_resumo", "nome_4md", "p", "q", "Ft"]].drop_duplicates()
    output = output.merge(factors_pq, on=["ano", "segmento", "fonte_resumo", "nome_4md"], how="left")
    if filtro_nome4md != "N" and filtro_nome4md in set(output["nome_4md"]): output = output[output["nome_4md"] == filtro_nome4md]
    if filtro_de_segmento != "N" and filtro_de_segmento in SEGMENTOS: output = output[output["segmento"] == filtro_de_segmento]
    return output.reset_index(drop=True)


def epe4md_proj_geracao(proj_mensal: pd.DataFrame | list[dict[str, Any]], ano_base: int, filtro_de_uf: str = "N",
                         filtro_de_segmento: str = "N", dir_dados_premissas: str | None = None) -> pd.DataFrame:
    monthly = records_to_dataframe(proj_mensal, "proj_mensal").copy()
    require_columns(monthly, ["data_conexao", "ano", "mes", "nome_4md", "segmento", "fonte_resumo", "pot_mes_mw", "adotantes_mes"], "proj_mensal")
    monthly["data_conexao"] = pd.to_datetime(monthly["data_conexao"])
    regions = load_workbook(ano_base, "tabela_dist_subs.xlsx", dir_dados_premissas)
    injection = load_workbook(ano_base, "injecao.xlsx", dir_dados_premissas)
    photovoltaic = load_workbook(ano_base, "fc_distribuidoras_mensal.xlsx", dir_dados_premissas)
    other = load_workbook(ano_base, "fc_outras_fontes.xlsx", dir_dados_premissas, "fc").melt(id_vars=["subsistema", "fonte_resumo"], var_name="mes", value_name="fc")
    other["mes"] = other["mes"].astype(int)
    monthly = monthly.merge(regions, on="nome_4md", how="left")
    if monthly[["uf", "subsistema"]].isna().any().any(): raise ValueError("Há distribuidoras sem UF ou subsistema em tabela_dist_subs.xlsx.")
    if filtro_de_uf != "N" and filtro_de_uf in set(monthly["uf"]): monthly = monthly[monthly["uf"] == filtro_de_uf]
    if filtro_de_segmento != "N" and filtro_de_segmento in SEGMENTOS: monthly = monthly[monthly["segmento"] == filtro_de_segmento]
    monthly = monthly[monthly["pot_mes_mw"] != 0].copy()
    if monthly.empty: return pd.DataFrame(columns=["data", "ano", "mes", "nome_4md", "subsistema", "uf", "segmento", "fonte_resumo", "energia_mwh", "energia_autoc_mwh", "energia_inj_mwh", "energia_mwmed", "pot_mes_mw", "adotantes_mes", "p", "q", "regiao"])
    # Each monthly installation produces through the requested horizon; this mirrors the R installation-to-operation expansion.
    final_year = int(monthly["ano"].max())
    operations = pd.date_range("2013-01-01", f"{final_year}-12-01", freq="MS")
    installations = monthly.assign(_key=1).merge(pd.DataFrame({"operacao": operations, "_key": 1}), on="_key").drop(columns="_key")
    installations["instalacao"] = installations["data_conexao"] + pd.Timedelta(days=14)
    installations = installations[installations["operacao"] > installations["instalacao"]]
    installations["mes_operacao"] = installations["operacao"].dt.month
    installations = installations.merge(other, left_on=["subsistema", "fonte_resumo", "mes_operacao"], right_on=["subsistema", "fonte_resumo", "mes"], how="left").merge(photovoltaic, left_on=["nome_4md", "mes_operacao"], right_on=["nome_4md", "mes"], how="left", suffixes=("", "_fotovoltaica"))
    installations["fc"] = np.where(installations["fonte_resumo"].eq("Fotovoltaica") & installations["segmento"].eq("comercial_at_remoto"), installations["fc_remoto"], np.where(installations["fonte_resumo"].eq("Fotovoltaica"), installations["fc_local"], installations["fc"]))
    if installations["fc"].isna().any(): raise ValueError("Fator de capacidade mensal ausente para uma instalação.")
    elapsed = (installations["operacao"] - installations["instalacao"]).dt.days.clip(upper=25 * 365)
    days = installations["operacao"].dt.days_in_month
    first_month = (installations["operacao"] - installations["instalacao"]).dt.days < 28
    operating_days = np.where(first_month, days - 15, days)
    degradation = (1 + .005) ** (1 / 365) - 1
    installations["energia_mwh"] = installations["pot_mes_mw"] * installations["fc"] * operating_days * 24 * np.where(installations["fonte_resumo"].eq("Fotovoltaica"), (1 - degradation) ** elapsed, 1)
    installations = installations.merge(injection, on=["segmento", "fonte_resumo"], how="left")
    if installations["fator_autoconsumo"].isna().any(): raise ValueError("Fator de autoconsumo ausente para uma fonte ou segmento.")
    installations["energia_autoc_mwh"] = installations["energia_mwh"] * installations["fator_autoconsumo"]
    installations["energia_inj_mwh"] = installations["energia_mwh"] * (1 - installations["fator_autoconsumo"])
    keys = ["operacao", "nome_4md", "subsistema", "uf", "segmento", "fonte_resumo"]
    energy = installations.groupby(keys, as_index=False)[["energia_mwh", "energia_autoc_mwh", "energia_inj_mwh"]].sum()
    power = monthly.groupby(["data_conexao", "nome_4md", "subsistema", "uf", "segmento", "fonte_resumo"], as_index=False)[["pot_mes_mw", "adotantes_mes"]].sum().rename(columns={"data_conexao": "operacao"})
    output = energy.merge(power, on=keys, how="outer").fillna({"pot_mes_mw": 0, "adotantes_mes": 0})
    output["data"] = output["operacao"].dt.date.astype(str)
    output["ano"] = output["operacao"].dt.year
    output["mes"] = output["operacao"].dt.month
    output["energia_mwmed"] = output["energia_mwh"] / (24 * output["operacao"].dt.days_in_month)
    fatores_difusao = monthly[["nome_4md", "segmento", "p", "q"]].drop_duplicates()
    output = output.merge(fatores_difusao, on=["nome_4md", "segmento"], how="left").merge(regions[["nome_4md", "subsistema", "uf", "regiao"]], on=["nome_4md", "subsistema", "uf"], how="left")
    return output[["data", "ano", "mes", "nome_4md", "subsistema", "uf", "segmento", "fonte_resumo", "energia_mwh", "energia_autoc_mwh", "energia_inj_mwh", "energia_mwmed", "pot_mes_mw", "adotantes_mes", "p", "q", "regiao"]].sort_values(["data", "nome_4md"]).reset_index(drop=True)


def epe4md_sumariza_resultados(resultados_mensais: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    results = records_to_dataframe(resultados_mensais, "resultados_mensais")
    require_columns(results, ["ano", "pot_mes_mw", "energia_mwh"], "resultados_mensais")
    output = results.groupby("ano", as_index=False).agg(pot_ano=("pot_mes_mw", lambda value: value.sum() / 1000), geracao_gwh=("energia_mwh", lambda value: value.sum() / 1000)).sort_values("ano")
    output["pot_acum"] = output["pot_ano"].cumsum()
    output["geracao_mwmed"] = output["geracao_gwh"] / 8.76
    return output


def epe4md_investimentos(resultados_mensais: pd.DataFrame | list[dict[str, Any]], ano_base: int, ano_max_resultado: int = 2050,
                          dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base, ano_max_resultado)
    results = records_to_dataframe(resultados_mensais, "resultados_mensais")
    power = results.groupby(["ano", "segmento", "fonte_resumo"], as_index=False)["pot_mes_mw"].sum().rename(columns={"pot_mes_mw": "pot_ano_mw"})
    photovoltaic_costs = load_workbook(ano_base, "custos.xlsx", dir_dados_premissas, "custos").assign(fonte_resumo="Fotovoltaica")
    other_costs = load_workbook(ano_base, "capex_historico_outras.xlsx", dir_dados_premissas).rename(columns={"custo_unitario": "custo_outras"})
    output = power.merge(photovoltaic_costs, on=["ano", "segmento", "fonte_resumo"], how="left").merge(other_costs, on="fonte_resumo", how="left")
    output["custo_unitario"] = output["custo_unitario"].fillna(output["custo_outras"])
    if output["custo_unitario"].isna().any(): raise ValueError("Custo unitário ausente para uma fonte, segmento ou ano.")
    output["investimento_ano_milhoes"] = output["pot_ano_mw"] * output["custo_unitario"]
    return output.drop(columns="custo_outras")


def epe4md_fatores_publicacao(dados: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    output = records_to_dataframe(dados, "dados")
    replacements = [("comercial_bt", "Comercial (BT)"), ("comercial_at_remoto", "Comercial Remoto (AT/BT)"), ("comercial_at", "Comercial (AT)"), ("residencial_remoto", "Residencial Remoto"), ("residencial", "Residencial")]
    for column in output.select_dtypes(include=["object", "string"]):
        for original, replacement in replacements:
            output[column] = output[column].str.replace(original, replacement, regex=False)
    return output


def epe4md_prepara_base(base_aneel: pd.DataFrame | list[dict[str, Any]], ano_base: int, resumida: bool = True,
                        dir_dados_premissas: str | None = None) -> pd.DataFrame:
    source = records_to_dataframe(base_aneel, "base_aneel").copy()
    source.columns = ["".join(character if character.isalnum() else "_" for character in column).strip("_").lower() for column in source.columns]
    require_columns(source, ["sig_agente", "cod_municipio_ibge", "sig_tipo_geracao", "dth_atualiza_cadastral_empreend", "dsc_porte", "sig_uf", "mda_potencia_instalada_kw", "qtd_uc_recebe_credito", "dsc_sub_grupo_tarifario", "dsc_classe_consumo", "sig_modalidade_empreendimento", "nom_municipio"], "base_aneel")
    source = source.dropna(subset=["sig_agente", "cod_municipio_ibge"])
    source["fonte_resumo"] = source["sig_tipo_geracao"].map({"UFV": "Fotovoltaica", "UTE": "Termelétrica", "EOL": "Eólica"}).fillna("Hidro")
    source["data_conexao"] = pd.to_datetime(source["dth_atualiza_cadastral_empreend"]).clip(lower=pd.Timestamp("2013-01-01"))
    source["ano"] = source["data_conexao"].dt.year
    source["mes"] = source["data_conexao"].dt.to_period("M").dt.to_timestamp()
    source["mini_micro"] = np.where(source["dsc_porte"].eq("Microgeracao"), "MicroGD", "MiniGD")
    names = load_workbook(ano_base, "nomes_dist_powerbi.xlsx", dir_dados_premissas)
    regions = load_workbook(ano_base, "tabela_dist_subs.xlsx", dir_dados_premissas)[["uf", "subsistema"]].drop_duplicates()
    segments = load_workbook(ano_base, "segmento.xlsx", dir_dados_premissas)
    source = source.merge(names, on="sig_agente", how="left").rename(columns={"sig_uf": "uf", "mda_potencia_instalada_kw": "potencia_instalada_k_w", "qtd_uc_recebe_credito": "qtde_u_csrecebem_os_creditos", "dsc_fonte_geracao": "fonte", "dsc_sub_grupo_tarifario": "subgrupo", "dsc_classe_consumo": "classe", "nom_municipio": "municipio"}).merge(regions, on="uf", how="left")
    source["potencia_mw"] = source["potencia_instalada_k_w"] / 1000
    source["atbt"] = np.where(source["subgrupo"].isin(["B1", "B2", "B3", "B4"]), "BT", "AT")
    source["local_remoto"] = np.where(source["sig_modalidade_empreendimento"].isin(["R", "C"]), "remoto", "local")
    source["classe"] = source["classe"].replace("Iluminação pública", "Ilum. Púb.")
    source["modalidade"] = source["sig_modalidade_empreendimento"].map({"P": "Geração na própria UC", "R": "Autoconsumo remoto", "C": "Geração compartilhada"}).fillna("Condomínios")
    source = source.merge(segments, on=["classe", "atbt", "local_remoto"], how="left")
    source["num_geradores"] = 1
    detailed_keys = ["mes", "ano", "nome_4md", "uf", "subsistema", "fonte_resumo", "classe", "subgrupo", "modalidade", "segmento", "mini_micro", "atbt", "local_remoto"]
    detailed = source.groupby(detailed_keys, as_index=False)[["qtde_u_csrecebem_os_creditos", "num_geradores", "potencia_instalada_k_w", "potencia_mw"]].sum().rename(columns={"mes": "data_conexao"})
    if not resumida: return detailed
    return detailed.groupby(["data_conexao", "ano", "nome_4md", "fonte_resumo", "segmento"], as_index=False)[["qtde_u_csrecebem_os_creditos", "num_geradores", "potencia_instalada_k_w", "potencia_mw"]].sum()


def epe4md_calcula(premissas_reg: pd.DataFrame | list[dict[str, Any]], ano_base: int, sequencial: bool = False,
                    filtro_de_uf: str = "N", filtro_nome4md: str = "N", filtro_de_segmento: str = "N",
                    filtro_de_custo_unitario_max: float | None = None, ano_max_resultado: int = 2050,
                    altera_sistemas_existentes: bool = False, ano_decisao_alteracao: int = 2023,
                    inflacao: float = .0375, taxa_desconto_nominal: float = .13, custo_reforco_rede: float = 200,
                    ano_troca_inversor: int = 11, pagamento_disponibilidade: float = .3, disponibilidade_kwh_mes: float = 100,
                    filtro_renda_domicilio: str = "maior_3sm", desconto_capex_local: float = 0, anos_desconto: int | list[int] = 0,
                    tx_cresc_grupo_a: float = .016, spb: float = .3, p_max: float = .01, q_max: float = 1,
                    filtro_comercial: float | None = None, ajuste_ano_corrente: bool = False, ultimo_mes_ajuste: int | None = None,
                    metodo_ajuste: str | None = None, dir_dados_premissas: str | None = None) -> pd.DataFrame:
    _validate_year(ano_base, ano_max_resultado)
    premises = records_to_dataframe(premissas_reg, "premissas_reg")
    cases = epe4md_casos_payback(ano_base, ano_max_resultado, inflacao, ano_troca_inversor, dir_dados_premissas=dir_dados_premissas)
    payback = epe4md_payback(cases, premises, ano_base, sequencial, filtro_de_uf, filtro_de_segmento, filtro_de_custo_unitario_max, altera_sistemas_existentes, ano_decisao_alteracao, inflacao, taxa_desconto_nominal, custo_reforco_rede, ano_troca_inversor, pagamento_disponibilidade, disponibilidade_kwh_mes, desconto_capex_local, anos_desconto, dir_dados_premissas)
    market = epe4md_mercado_potencial(ano_base, filtro_renda_domicilio, filtro_comercial, tx_cresc_grupo_a, dir_dados_premissas)
    optimized = epe4md_calibra_curva_s(payback, market, ano_base, ano_max_resultado, spb, p_max, q_max, dir_dados_premissas)
    adopters = epe4md_proj_adotantes(optimized, market, ano_base, dir_dados_premissas)
    capacity = epe4md_proj_potencia(adopters, ano_base, dir_dados_premissas)
    monthly = epe4md_proj_mensal(capacity, ano_base, filtro_nome4md, filtro_de_segmento, ano_max_resultado, ajuste_ano_corrente, ultimo_mes_ajuste, metodo_ajuste, dir_dados_premissas)
    return epe4md_proj_geracao(monthly, ano_base, filtro_de_uf, filtro_de_segmento, dir_dados_premissas)
