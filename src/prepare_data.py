"""Extrai uma fotografia mínima das fontes locais e reconstrói o painel.

Uso cotidiano (offline): python src/prepare_data.py
Nova extração: python src/prepare_data.py --original-root CAMINHO
Os dados originais não são alterados. País e ano são chaves, não preditores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COUNTRIES = {"BR": "BRA", "CN": "CHN", "US": "USA"}
YEARS = range(2004, 2025)
SECTORS = {"SL.AGR.EMPL.ZS": "agriculture", "SL.IND.EMPL.ZS": "industry", "SL.SRV.EMPL.ZS": "services"}
INCOME = {"p0p50": "income_bottom50", "p50p90": "income_middle40", "p90p100": "income_top10"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_sources(original: Path, root: Path) -> None:
    """Lê apenas os arquivos necessários; congela os registros selecionados."""
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ledger = []

    def read(relative: str, **kwargs) -> pd.DataFrame:
        source = original / relative
        table = pd.read_csv(source, **kwargs)
        ledger.append({"file": relative.replace("\\", "/"), "bytes": source.stat().st_size,
                       "sha256": sha256(source), "source_rows": len(table)})
        return table

    gdp_folder = "API_NY.GDP.PCAP.KD_DS2_en_csv_v2_329799"
    gdp = read(f"{gdp_folder}/{gdp_folder}.csv", skiprows=4)
    gdp = gdp.loc[gdp["Country Code"].isin(COUNTRIES.values()) & gdp["Indicator Code"].eq("NY.GDP.PCAP.KD")]
    gdp = gdp.melt(id_vars=["Country Name", "Country Code", "Indicator Code"], value_vars=[str(y) for y in YEARS],
                   var_name="year", value_name="gdp_per_capita")
    gdp = gdp.rename(columns={"Country Code": "country", "Country Name": "country_name", "Indicator Code": "indicator"})
    gdp.to_csv(raw / "wb_gdp.csv", index=False)
    meta = read(f"{gdp_folder}/Metadata_Indicator_{gdp_folder}.csv")
    meta.to_csv(raw / "wb_gdp_metadata.csv", index=False)

    ilo_tables = []
    for stem, field in [("GDP_211P_NOC_NB", "productivity"), ("SDG_1041_NOC_RT", "labor_share")]:
        name = f"{stem}_A-20260919T1910.csv"
        table = read(f"{name}/{name}")
        selected = table.loc[table["ref_area"].isin(COUNTRIES.values()) & table["time"].isin(YEARS)].copy()
        selected = selected.rename(columns={"ref_area": "country", "time": "year", "obs_value": "value"})
        selected["feature"] = field
        if "obs_status" not in selected:
            selected["obs_status"] = ""
        ilo_tables.append(selected[["country", "year", "source", "indicator", "value", "obs_status", "feature"]])
    pd.concat(ilo_tables, ignore_index=True).to_csv(raw / "ilostat.csv", index=False)

    sectors = []
    for indicator, field in SECTORS.items():
        table = read(f"world_bank_sector_employment/{indicator}.csv")
        table = table.loc[table["country"].isin(COUNTRIES.values()) & table["year"].isin(YEARS)].copy()
        table["feature"] = field
        sectors.append(table)
    pd.concat(sectors, ignore_index=True).to_csv(raw / "wb_sectors.csv", index=False)

    wid_tables, wid_metadata = [], []
    for iso2, iso3 in COUNTRIES.items():
        table = read(f"wid_all_data/WID_data_{iso2}.csv", sep=";", low_memory=False)
        table = table.loc[table["variable"].eq("sptincj992") & table["percentile"].isin(INCOME) & table["year"].isin(YEARS)].copy()
        table["country"] = iso3
        table["feature"] = table["percentile"].map(INCOME)
        # Na origem, participação é fração; no painel, pontos percentuais.
        table["value"] = pd.to_numeric(table["value"], errors="raise") * 100
        wid_tables.append(table)
        metadata = read(f"wid_all_data/WID_metadata_{iso2}.csv", sep=";", low_memory=False)
        wid_metadata.append(metadata.loc[metadata["variable"].eq("sptincj992")])
    pd.concat(wid_tables, ignore_index=True).to_csv(raw / "wid_income.csv", index=False)
    pd.concat(wid_metadata, ignore_index=True).to_csv(raw / "wid_metadata.csv", index=False)

    manifest = {"extracted_at_utc": datetime.now(timezone.utc).isoformat(), "period": [2004, 2024],
                "countries": list(COUNTRIES.values()), "selection": "Local snapshot, no online refresh",
                "original_files": ledger,
                "snapshot_files": {p.name: sha256(p) for p in sorted(raw.glob("*.csv")) if p.name != "painel_fontes.csv"}}
    (raw / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def unique(table: pd.DataFrame, keys: list[str], name: str) -> None:
    if table.duplicated(keys).any():
        raise ValueError(f"{name}: chave duplicada {keys}; resolver a fonte antes de modelar.")


def build_panel(root: Path) -> pd.DataFrame:
    """Reconstrói o painel somente a partir das pequenas tabelas congeladas."""
    raw = root / "data" / "raw"
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["snapshot_files"].items():
        if sha256(raw / filename) != expected:
            raise ValueError(f"Integridade da fotografia alterada: {filename}")
    gdp = pd.read_csv(raw / "wb_gdp.csv")
    ilo = pd.read_csv(raw / "ilostat.csv", keep_default_na=False)
    sectors = pd.read_csv(raw / "wb_sectors.csv")
    income = pd.read_csv(raw / "wid_income.csv")
    unique(gdp, ["country", "year"], "PIB")
    for name, table in [("ILO", ilo), ("setores", sectors), ("renda", income)]:
        unique(table, ["country", "year", "feature"], name)
    index = pd.MultiIndex.from_product([sorted(COUNTRIES.values()), YEARS], names=["country", "year"])
    panel = pd.DataFrame(index=index).join(gdp.set_index(["country", "year"])[["gdp_per_capita"]])
    for table in [ilo, sectors, income]:
        wide = table.pivot(index=["country", "year"], columns="feature", values="value")
        panel = panel.join(wide)
    panel = panel.apply(pd.to_numeric, errors="raise").reset_index()
    feature_columns = panel.columns.difference(["country", "year"])
    if panel[feature_columns].isna().any().any():
        raise ValueError("Fotografia esperada completa: há observações faltantes nas fontes.")
    if len(panel) != 63 or len(feature_columns) != 9:
        raise ValueError("Painel fora do contrato: esperado 63 linhas e 9 indicadores.")
    for cols in [["agriculture", "industry", "services"], list(INCOME.values())]:
        if (panel[cols] <= 0).any().any() or (panel[cols].sum(axis=1) - 100).abs().max() > .1:
            raise ValueError(f"Composição inválida em {cols}")
    if (panel[["gdp_per_capita", "productivity"]] <= 0).any().any():
        raise ValueError("Indicador monetário não positivo.")
    if not panel["labor_share"].between(0, 100).all():
        raise ValueError("Participação do trabalho fora de 0-100%.")
    panel.to_csv(raw / "painel_fontes.csv", index=False, float_format="%.12g")
    return panel


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.original_root:
        extract_sources(args.original_root, args.root)
    frame = build_panel(args.root)
    print(f"Painel validado: {frame.shape[0]} país-anos, {frame.shape[1] - 2} indicadores, sem faltantes.")
