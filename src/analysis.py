"""Pipeline reprodutível de agrupamento de perfis socioeconômicos (Opção B).

Execute ``python src/analysis.py --root .`` na pasta do projeto. A unidade de
análise é país-ano; país e ano são identificadores e nunca entram nos modelos.
Os blocos de validação temporal retiram quatro anos comuns a todos os países.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import RobustScaler, StandardScaler


RAW_COLUMNS = [
    "gdp_per_capita", "productivity", "labor_share", "agriculture",
    "industry", "services", "income_bottom50", "income_middle40", "income_top10",
]
FEATURE_NAMES = [
    "log_gdp_per_capita", "log_productivity", "labor_share",
    "ilr_agriculture_industry", "ilr_agri_industry_services",
    "ilr_bottom50_middle40", "ilr_bottom_middle_top10",
]
FEATURE_LABELS = [
    "ln(PIB per capita)", "ln(Produtividade)", "Renda do trabalho / PIB",
    "ILR agro / indústria", "ILR √(agro·ind.) / serviços",
    "ILR renda B50 / M40", "ILR renda √(B50·M40) / T10",
]
COLORS = ["#2572a3", "#e18d26", "#388b66", "#a75e9b", "#c05552", "#7d8061"]
COUNTRY_NAMES = {"BRA": "Brasil", "CHN": "China", "USA": "Estados Unidos"}


def _json_safe(obj: Any) -> Any:
    """Converta tipos NumPy e valores não finitos para JSON estrito."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if math.isfinite(float(obj)) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _read_data(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Leia o painel e detecte erros de estrutura antes de qualquer ajuste."""
    if not path.exists():
        raise FileNotFoundError(f"Base não encontrada: {path}. Gere data/raw/painel_fontes.csv primeiro.")
    df = pd.read_csv(path)
    required = ["country", "year", *RAW_COLUMNS]
    absent = sorted(set(required) - set(df.columns))
    if absent:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(absent)}")
    df = df[required].copy()
    if df[["country", "year"]].isna().any().any():
        raise ValueError("País e ano não podem estar ausentes.")
    df["country"] = df["country"].astype(str).str.upper().str.strip()
    numeric_year = pd.to_numeric(df["year"], errors="raise")
    if not np.equal(numeric_year, np.floor(numeric_year)).all():
        raise ValueError("Anos devem ser números inteiros.")
    df["year"] = numeric_year.astype(int)
    if df.duplicated(["country", "year"]).any():
        raise ValueError("Há chaves país-ano repetidas; revise a integração das fontes.")
    if set(df["country"]) != {"BRA", "CHN", "USA"}:
        raise ValueError("O painel deve conter BRA, CHN e USA.")
    expected = {(c, y) for c in ["BRA", "CHN", "USA"] for y in range(2004, 2025)}
    observed = set(df[["country", "year"]].itertuples(index=False, name=None))
    if observed != expected:
        raise ValueError("O painel deve conter exatamente os 63 pares país-ano de 2004 a 2024.")
    for col in RAW_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="raise")
        values = df[col].dropna().to_numpy()
        if not np.isfinite(values).all():
            raise ValueError(f"Valores infinitos na variável {col}.")
        if len(values) == 0:
            raise ValueError(f"Variável inteiramente ausente: {col}.")
        if (values <= 0).any():
            raise ValueError(f"{col} deve conter valores estritamente positivos para este pipeline.")
    if (df[["labor_share", "agriculture", "industry", "services", "income_bottom50", "income_middle40", "income_top10"]] > 100).any().any():
        raise ValueError("Participações devem ser fornecidas em porcentagem, no intervalo (0, 100].")
    missing = df[RAW_COLUMNS].isna().sum()
    closure_diagnostics = {}
    for name, cols in {
        "setores": ["agriculture", "industry", "services"],
        "renda": ["income_bottom50", "income_middle40", "income_top10"],
    }.items():
        totals = df[cols].sum(axis=1, min_count=3).dropna()
        if ((totals - 100).abs() > 2).any():
            raise ValueError(f"Composição de {name} não soma aproximadamente 100%; confira a unidade.")
        closure_diagnostics[name] = {"soma_min": totals.min(), "soma_max": totals.max()}
    quality = {
        "n_rows": len(df), "n_countries": df["country"].nunique(),
        "year_min": df["year"].min(), "year_max": df["year"].max(),
        "missing_by_column": missing.to_dict(), "missing_total": missing.sum(),
        "duplicate_country_year": 0, "composition_totals_before_closure": closure_diagnostics,
    }
    return df.sort_values(["country", "year"]).reset_index(drop=True), quality


class FeatureTransform:
    """Impute, transforme composições por ILR e escale usando somente o ajuste.

    As duas coordenadas ILR de cada composição de três partes são ortonormais.
    O fechamento em 100% corrige arredondamentos e não muda as razões.
    Medianas e parâmetros de escala são aprendidos apenas nas linhas de treino.
    """

    def __init__(self, columns: list[str] | None = None, robust: bool = False):
        self.columns = list(FEATURE_NAMES if columns is None else columns)
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        self.scaler = RobustScaler() if robust else StandardScaler()

    def _engineer(self, values: np.ndarray) -> pd.DataFrame:
        a = pd.DataFrame(values, columns=RAW_COLUMNS)
        out = pd.DataFrame({
            "log_gdp_per_capita": np.log(a["gdp_per_capita"]),
            "log_productivity": np.log(a["productivity"]),
            "labor_share": a["labor_share"],
        })
        for cols, names in [
            (["agriculture", "industry", "services"], FEATURE_NAMES[3:5]),
            (["income_bottom50", "income_middle40", "income_top10"], FEATURE_NAMES[5:7]),
        ]:
            composition = a[cols].to_numpy()
            composition = composition / composition.sum(axis=1, keepdims=True)
            logs = np.log(composition)
            out[names[0]] = (logs[:, 0] - logs[:, 1]) / np.sqrt(2)
            out[names[1]] = np.sqrt(2 / 3) * ((logs[:, 0] + logs[:, 1]) / 2 - logs[:, 2])
        return out[self.columns]

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """Aprenda imputação e escala no subconjunto fornecido."""
        values = self.imputer.fit_transform(df[RAW_COLUMNS])
        if (values <= 0).any():
            raise ValueError("A imputação produziu valor não positivo, incompatível com log e ILR.")
        self.engineered_ = self._engineer(values)
        return self.scaler.fit_transform(self.engineered_)

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """Aplique parâmetros já aprendidos a outras observações."""
        return self.scaler.transform(self._engineer(self.imputer.transform(df[RAW_COLUMNS])))


def _fit(config: dict[str, Any], x: np.ndarray, seed: int = 42) -> np.ndarray:
    """Ajuste um dos algoritmos sem usar identificadores ou rótulos externos."""
    if config["family"] == "KMeans":
        return KMeans(n_clusters=int(config["k"]), n_init=50, random_state=seed).fit_predict(x)
    if config["family"] == "Ward":
        return AgglomerativeClustering(n_clusters=int(config["k"]), linkage="ward").fit_predict(x)
    if config["family"] == "DBSCAN":
        return DBSCAN(eps=float(config["eps"]), min_samples=int(config["min_samples"])).fit_predict(x)
    raise ValueError(f"Algoritmo desconhecido: {config['family']}")


def _metrics(x: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    """Meça grupos; métricas do DBSCAN com ruído usam só pontos agrupados."""
    keep = labels != -1
    groups, counts = np.unique(labels[keep], return_counts=True)
    metrics = {
        "n_clusters": len(groups), "smallest_cluster": int(counts.min()) if len(counts) else 0,
        "coverage": float(keep.mean()), "noise_count": int((~keep).sum()),
        "metric_scope": "painel_completo" if keep.all() else "somente_sem_ruido",
        "silhouette": None, "davies_bouldin": None, "calinski_harabasz": None,
    }
    if 2 <= len(groups) < int(keep.sum()):
        metrics.update(
            silhouette=float(silhouette_score(x[keep], labels[keep])),
            davies_bouldin=float(davies_bouldin_score(x[keep], labels[keep])),
            calinski_harabasz=float(calinski_harabasz_score(x[keep], labels[keep])),
        )
    metrics["eligible"] = bool(
        keep.all() and 2 <= len(groups) <= 6 and metrics["smallest_cluster"] >= 4
        and metrics["silhouette"] is not None
    )
    return metrics


def _grid(x: np.ndarray) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Avalie as 34 configurações e mantenha toda a busca auditável."""
    configs = [
        {"family": family, "k": k}
        for family in ["KMeans", "Ward"] for k in range(2, 7)
    ] + [
        {"family": "DBSCAN", "eps": eps, "min_samples": minimum}
        for eps in [0.35, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 2.0]
        for minimum in [3, 4, 5]
    ]
    rows = []
    for config_id, config in enumerate(configs):
        labels = _fit(config, x)
        rows.append({"config_id": config_id, **config, **_metrics(x, labels)})
    return pd.DataFrame(rows), configs


def _best(rows: pd.DataFrame, require_full: bool = True) -> pd.Series | None:
    """Ordene por silhouette decrescente e Davies–Bouldin crescente."""
    if require_full:
        candidates = rows[rows["eligible"]]
    else:
        candidates = rows[
            rows["silhouette"].notna() & rows["n_clusters"].between(2, 6)
            & (rows["smallest_cluster"] >= 4)
        ]
    if candidates.empty:
        return None
    return candidates.sort_values(
        ["silhouette", "davies_bouldin", "config_id"], ascending=[False, True, True]
    ).iloc[0]


def _canonical(labels: np.ndarray, df: pd.DataFrame) -> np.ndarray:
    """Numere os grupos por mediana crescente de PIB per capita (zero em diante)."""
    group_order = sorted(
        [int(group) for group in np.unique(labels) if group != -1],
        key=lambda group: (float(df.loc[labels == group, "gdp_per_capita"].median()), group),
    )
    mapping = {group: i for i, group in enumerate(group_order)}
    return np.array([mapping.get(int(group), -1) for group in labels], dtype=int)


def _robustness(
    df: pd.DataFrame, x: np.ndarray, grid: pd.DataFrame, configs: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Refaça o pipeline em 18 exclusões de blocos temporais comuns de 4 anos.

    ARI compara a partição do subconjunto remanescente à partição de referência
    do painel completo restrita às mesmas linhas. É estabilidade descritiva,
    não acurácia preditiva nem validação com rótulos verdadeiros.
    """
    block_rows, seed_rows, summaries = [], [], []
    best_configs = []
    for family in ["KMeans", "Ward", "DBSCAN"]:
        family_grid = grid[grid["family"] == family]
        best = _best(family_grid)
        if best is None and family == "DBSCAN":
            best = _best(family_grid, require_full=False)
        if best is not None:
            best_configs.append((family, configs[int(best["config_id"])]))
    for family, config in best_configs:
        reference = _fit(config, x)
        for start in range(2004, 2022):
            keep = ~df["year"].between(start, start + 3).to_numpy()
            subset = df.loc[keep].reset_index(drop=True)
            sub_x = FeatureTransform().fit_transform(subset)
            labels = _fit(config, sub_x)
            m = _metrics(sub_x, labels)
            valid = m["silhouette"] is not None
            # Para DBSCAN, o ruído (-1) é explicitamente uma categoria na ARI.
            ari = float(adjusted_rand_score(reference[keep], labels)) if valid else None
            block_rows.append({
                "family": family, **config, "excluded_start": start,
                "excluded_end": start + 3, "n_removed": int((~keep).sum()),
                "n_retained": int(keep.sum()), "ari": ari, "valid": valid,
                "degenerate_reason": "" if valid else "menos_de_dois_grupos_ou_todos_pontos_isolados",
                **m,
            })
        family_results = pd.DataFrame(block_rows)
        family_results = family_results[family_results["family"] == family]
        valid_ari = family_results["ari"].dropna()
        summaries.append({
            "family": family, "config": config, "n_tests": len(family_results),
            "valid_tests": int(family_results["valid"].sum()),
            "degenerate_tests": int((~family_results["valid"]).sum()),
            "ari_mean": valid_ari.mean(), "ari_min": valid_ari.min(),
            "ari_max": valid_ari.max(), "ari_std": valid_ari.std(ddof=0),
            "coverage_mean": family_results["coverage"].mean(),
            "note": "ARI inclui a categoria ruído quando presente; não há rótulos de referência externos.",
        })
        if family == "KMeans":
            for seed in range(20):
                labels = _fit(config, x, seed=seed)
                seed_rows.append({
                    "seed": seed, "k": config["k"],
                    "ari_vs_seed42": adjusted_rand_score(reference, labels),
                    **_metrics(x, labels),
                })
    return pd.DataFrame(block_rows), pd.DataFrame(seed_rows), summaries


def _sensitivity(
    df: pd.DataFrame, config: dict[str, Any], reference: np.ndarray,
) -> pd.DataFrame:
    """Teste dependência de renda, nível econômico e regra de escalonamento."""
    variants = [
        ("completo_standard", FEATURE_NAMES, False),
        ("sem_composicao_renda", FEATURE_NAMES[:5], False),
        ("sem_pib_e_produtividade", FEATURE_NAMES[2:], False),
        ("sem_participacao_trabalho", [name for name in FEATURE_NAMES if name != "labor_share"], False),
        ("completo_robust_scaler", FEATURE_NAMES, True),
    ]
    rows = []
    for name, features, robust in variants:
        x = FeatureTransform(columns=features, robust=robust).fit_transform(df)
        labels = _fit(config, x)
        metrics = _metrics(x, labels)
        rows.append({
            "variant": name, "n_features": len(features),
            "features": ";".join(features), "family": config["family"],
            "ari_vs_selected": float(adjusted_rand_score(reference, labels)), **metrics,
        })
    return pd.DataFrame(rows)


def _save_figure(fig: plt.Figure, path: Path) -> None:
    """Salve figura com margens automáticas e libere memória."""
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plots(
    root: Path, df: pd.DataFrame, x: np.ndarray, labels: np.ndarray,
    grid: pd.DataFrame, scores: np.ndarray, explained: np.ndarray,
) -> None:
    """Produza seis figuras de EDA, seleção e interpretação dos agrupamentos."""
    figdir = root / "figures"
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    countries = list(COUNTRY_NAMES)
    fig, axes = plt.subplots(2, 3, figsize=(14, 7.6), layout="constrained")
    panels = [
        ("gdp_per_capita", "PIB per capita (US$ constantes de 2015)"),
        ("productivity", "PIB por pessoa ocupada (PPC, US$ int. 2021)"),
        ("labor_share", "Participação da renda do trabalho no PIB (%)"),
        ("agriculture", "Agropecuária no emprego total (%)"),
        ("income_bottom50", "Renda dos 50% mais pobres (%)"),
        ("income_top10", "Renda dos 10% mais ricos (%)"),
    ]
    for ax, (col, title) in zip(axes.flat, panels):
        for i, country in enumerate(countries):
            a = df[df["country"] == country]
            ax.plot(a["year"], a[col], color=COLORS[i], label=COUNTRY_NAMES[country], lw=2)
        ax.set_title(title, fontsize=11)
        ax.grid(alpha=0.2)
        ax.set_xticks(range(2004, 2025, 4))
        ax.tick_params(axis="x", rotation=30)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Evolução dos indicadores | 63 observações país-ano, 2004–2024", fontsize=15)
    _save_figure(fig, figdir / "01_eda_series.png")

    corr = pd.DataFrame(x, columns=FEATURE_LABELS).corr()
    fig, ax = plt.subplots(figsize=(10, 8), layout="constrained")
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(7), FEATURE_LABELS, rotation=52, ha="right")
    ax.set_yticks(range(7), FEATURE_LABELS)
    for i in range(7):
        for j in range(7):
            value = corr.iloc[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white" if abs(value) > .65 else "#202020", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=.046, pad=.04, label="Correlação de Pearson")
    ax.set_title("Correlação entre as sete variáveis do modelo", pad=14)
    _save_figure(fig, figdir / "02_correlacao_features.png")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    for family, color in [("KMeans", COLORS[0]), ("Ward", COLORS[1])]:
        a = grid[grid["family"] == family].sort_values("k")
        for ax, col, title in zip(axes, ["silhouette", "davies_bouldin", "calinski_harabasz"],
                                  ["Silhouette (maior é melhor)", "Davies–Bouldin (menor é melhor)", "Calinski–Harabasz (maior é melhor)"]):
            ax.plot(a["k"], a[col], marker="o", color=color, label=family)
            excluded = a[~a["eligible"]]
            ax.scatter(excluded["k"], excluded[col], marker="x", color="#222222", s=90, lw=2, zorder=4)
            ax.set_title(title, fontsize=11)
            ax.set_xlabel("Número de grupos (k)")
            ax.set_xticks(range(2, 7))
            ax.grid(alpha=.2)
    from matplotlib.lines import Line2D
    handles, legend_labels = axes[0].get_legend_handles_labels()
    handles.append(Line2D([0], [0], marker="x", color="#222222", linestyle="none", markersize=8))
    legend_labels.append("Excluído: menor grupo < 4")
    axes[0].legend(handles, legend_labels, frameon=False, fontsize=8)
    fig.suptitle("Comparação de partições completas | seleção exige grupos com pelo menos 4 observações", fontsize=13)
    _save_figure(fig, figdir / "03_busca_k.png")

    fig, ax = plt.subplots(figsize=(10, 6.8), layout="constrained")
    markers = {"BRA": "o", "CHN": "s", "USA": "^"}
    for country in countries:
        mask = df["country"].eq(country).to_numpy()
        points = scores[mask]
        ax.plot(points[:, 0], points[:, 1], color="#a4adb6", lw=1, alpha=.7, zorder=1)
        for group in sorted(set(labels)):
            keep = mask & (labels == group)
            if keep.any():
                ax.scatter(scores[keep, 0], scores[keep, 1], s=65, marker=markers[country],
                           c=[COLORS[int(group) % len(COLORS)]] if group != -1 else "#aaaaaa",
                           edgecolor="white", lw=.6, zorder=2)
        ids = np.flatnonzero(mask)
        for index in [ids[0], ids[-1]]:
            ax.annotate(f"{COUNTRY_NAMES[country]} {df.iloc[index]['year']}", scores[index],
                        xytext=(5, 5), textcoords="offset points", fontsize=8)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS[g], label=f"Grupo {g + 1}", markersize=8) for g in sorted(set(labels)) if g >= 0]
    handles += [Line2D([0], [0], marker=markers[c], color="#777777", linestyle="none", label=COUNTRY_NAMES[c], markersize=7) for c in countries]
    ax.legend(handles=handles, fontsize=9, frameon=False, loc="best")
    ax.set_xlabel(f"Componente principal 1 ({explained[0]:.1%} da variância)")
    ax.set_ylabel(f"Componente principal 2 ({explained[1]:.1%} da variância)")
    ax.set_title(f"PCA para visualização | variância acumulada: {explained.sum():.1%}\nAgrupamento calculado no espaço original de sete variáveis")
    ax.grid(alpha=.18)
    _save_figure(fig, figdir / "04_pca_clusters.png")

    profiles = pd.DataFrame(x, columns=FEATURE_LABELS).assign(cluster=labels).groupby("cluster").median()
    fig, ax = plt.subplots(figsize=(12, max(3.2, 1 + len(profiles) * .8)), layout="constrained")
    bound = max(1, float(np.abs(profiles.values).max()))
    im = ax.imshow(profiles, cmap="RdBu_r", vmin=-bound, vmax=bound, aspect="auto")
    ax.set_xticks(range(7), FEATURE_LABELS, rotation=35, ha="right")
    ax.set_yticks(range(len(profiles)), [f"Grupo {g+1} (n={(labels == g).sum()})" for g in profiles.index])
    for i in range(len(profiles)):
        for j in range(7):
            value = profiles.iloc[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white" if abs(value) > bound * .65 else "#202020", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=.025, pad=.02, label="Mediana da variável padronizada (z)")
    ax.set_title("Perfis dos grupos | ordenados pelo PIB per capita mediano", pad=12)
    _save_figure(fig, figdir / "05_perfis_heatmap.png")

    fig, axes = plt.subplots(3, 1, figsize=(13, 6.2), sharex=True, layout="constrained")
    for ax, country in zip(axes, countries):
        mask = df["country"].eq(country).to_numpy()
        a = df.loc[mask]
        cluster = labels[mask]
        ax.plot(a["year"], cluster + 1, color="#adb5bd", lw=1.5, zorder=1)
        ax.scatter(a["year"], cluster + 1, c=[COLORS[g % len(COLORS)] for g in cluster], s=65, zorder=2)
        ax.set_yticks(range(1, len(set(labels)) + 1))
        ax.set_ylim(.6, len(set(labels)) + .4)
        ax.set_ylabel(COUNTRY_NAMES[country])
        ax.grid(axis="x", alpha=.18)
    axes[-1].set_xticks(range(2004, 2025, 2))
    axes[-1].set_xlabel("Ano")
    fig.suptitle("Trajetórias país-ano nos grupos | escala vertical indica somente a categoria", fontsize=14)
    _save_figure(fig, figdir / "06_trajetorias_clusters.png")


def run_analysis(root: Path) -> dict[str, Any]:
    """Execute o estudo e salve resultados tabulares, figuras e resumo JSON.

    A seleção principal compara apenas partições de cobertura de 100%, entre
    dois e seis grupos, com no mínimo quatro observações em cada grupo.
    A silhouette de DBSCAN com ruído é exploratória e nunca disputa diretamente
    a seleção com métricas de partições que cobrem o painel completo.
    """
    root = Path(root).resolve()
    df, quality = _read_data(root / "data" / "raw" / "painel_fontes.csv")
    for folder in [root / "results", root / "figures", root / "data" / "processed"]:
        folder.mkdir(parents=True, exist_ok=True)
    transform = FeatureTransform()
    x = transform.fit_transform(df)
    grid, configs = _grid(x)
    selected = _best(grid)
    if selected is None:
        raise RuntimeError("Nenhuma configuração atende aos critérios pré-definidos de seleção.")
    config = configs[int(selected["config_id"])]
    labels = _canonical(_fit(config, x), df)
    baseline = grid[(grid["family"] == "KMeans") & (grid["k"] == 2)].iloc[0]
    db_exploratory = _best(grid[grid["family"] == "DBSCAN"], require_full=False)
    blocks, seeds, robustness = _robustness(df, x, grid, configs)
    sensitivity = _sensitivity(df, config, labels)
    pca = PCA(n_components=2, svd_solver="full")
    scores = pca.fit_transform(x)
    processed = df.copy()
    processed["cluster"] = labels + 1
    processed["pc1"] = scores[:, 0]
    processed["pc2"] = scores[:, 1]
    engineered = transform.engineered_.copy()
    transformed = pd.concat([df[["country", "year"]], engineered], axis=1)
    for j, col in enumerate(FEATURE_NAMES):
        transformed[f"z_{col}"] = x[:, j]
    transformed["cluster"] = labels + 1
    profiles = df.assign(cluster=labels + 1).groupby("cluster")[RAW_COLUMNS].median()
    profiles.insert(0, "n_observations", pd.Series(labels + 1).value_counts().reindex(profiles.index))
    profiles.insert(1, "countries", df.assign(cluster=labels + 1).groupby("cluster")["country"].agg(lambda a: ";".join(sorted(set(a)))))
    for j, col in enumerate(FEATURE_NAMES):
        profiles[f"median_z_{col}"] = pd.DataFrame({"cluster": labels + 1, "value": x[:, j]}).groupby("cluster")["value"].median()
    country_counts = pd.crosstab(processed["country"], processed["cluster"])
    transitions = []
    for country, a in processed.groupby("country"):
        previous = None
        for row in a.sort_values("year").itertuples():
            if previous is not None and row.cluster != previous:
                transitions.append({"country": country, "year": row.year, "from_cluster": previous, "to_cluster": row.cluster})
            previous = row.cluster
    grid.to_csv(root / "results" / "grid_modelos.csv", index=False)
    blocks.to_csv(root / "results" / "robustez_blocos.csv", index=False)
    seeds.to_csv(root / "results" / "robustez_sementes.csv", index=False)
    sensitivity.to_csv(root / "results" / "sensibilidade.csv", index=False)
    country_counts.to_csv(root / "results" / "contagem_pais_cluster.csv")
    pd.DataFrame(transitions, columns=["country", "year", "from_cluster", "to_cluster"]).to_csv(root / "results" / "transicoes.csv", index=False)
    processed.to_csv(root / "data" / "processed" / "painel_clusters.csv", index=False)
    transformed.to_csv(root / "data" / "processed" / "transformed.csv", index=False)
    profiles.to_csv(root / "data" / "processed" / "perfis.csv")
    pd.DataFrame(pca.components_.T, index=FEATURE_NAMES, columns=["pc1", "pc2"]).to_csv(root / "results" / "pca_loadings.csv", index_label="feature")
    df[RAW_COLUMNS].describe().T.to_csv(root / "results" / "estatisticas_descritivas.csv", index_label="variable")
    pd.DataFrame(x, columns=FEATURE_NAMES).corr().to_csv(root / "results" / "correlacao_features.csv", index_label="feature")
    summary = {
        "quality": quality,
        "features": FEATURE_NAMES,
        "n_features": len(FEATURE_NAMES),
        "feature_notes": {
            "log": "Logaritmo natural de PIB per capita e produtividade.",
            "ilr_1": "ln(parte1/parte2) / sqrt(2)",
            "ilr_2": "sqrt(2/3) * ln(sqrt(parte1*parte2)/parte3)",
            "composition_order_sectors": ["agriculture", "industry", "services"],
            "composition_order_income": ["income_bottom50", "income_middle40", "income_top10"],
            "scaling": "StandardScaler; ajustado novamente em cada subconjunto de robustez.",
            "identifiers": "country e year nunca entram no espaço de atributos.",
            "imputation": "Mediana aprendida somente no subconjunto de ajuste; não acionada se a base está completa.",
        },
        "selection_rule": "Cobertura 100%, 2 a 6 grupos, menor grupo >=4; maior silhouette, desempate por menor Davies–Bouldin.",
        "n_configurations": len(grid),
        "n_eligible": int(grid["eligible"].sum()),
        "selected": {"config": config, "metrics": selected.to_dict()},
        "baseline": {"config": {"family": "KMeans", "k": 2}, "metrics": baseline.to_dict()},
        "silhouette_gain_vs_baseline": float(selected["silhouette"] - baseline["silhouette"]),
        "dbscan_exploratory": None if db_exploratory is None else {
            "config": configs[int(db_exploratory["config_id"])], "metrics": db_exploratory.to_dict(),
            "warning": "Se há ruído, silhouette é calculada apenas no subconjunto agrupado e não comparada diretamente à seleção principal.",
        },
        "robustness_block_method": "Todos os 18 blocos contíguos de quatro anos, de 2004–2007 a 2021–2024, excluídos simultaneamente de BRA, CHN e USA (12 linhas por bloco). Reajuste completo sem as linhas excluídas; ARI nas 51 linhas remanescentes versus partição de referência restrita.",
        "robustness": robustness,
        "seed_sensitivity": {
            "n_seeds": len(seeds), "ari_min": seeds["ari_vs_seed42"].min(),
            "ari_mean": seeds["ari_vs_seed42"].mean(),
        },
        "sensitivity": sensitivity.to_dict(orient="records"),
        "pca_explained_variance_ratio": pca.explained_variance_ratio_,
        "pca_total_explained_2d": pca.explained_variance_ratio_.sum(),
        "cluster_counts": processed["cluster"].value_counts().sort_index().to_dict(),
        "country_cluster_counts": country_counts.to_dict(orient="index"),
        "cluster_profiles_medians": profiles.reset_index().to_dict(orient="records"),
        "transitions": transitions,
        "limitations": [
            "Somente três países e 21 anos: resultados descritivos do painel selecionado, sem representatividade mundial.",
            "Observações sucessivas de um país são dependentes; estabilidade por blocos não fornece inferência causal nem intervalos de confiança.",
            "Indicadores econômicos correlacionados podem aumentar implicitamente o peso de certas dimensões; análise de sensibilidade documentada.",
            "As métricas internas usam geometria dos próprios atributos, sem verdade externa para confirmar os grupos.",
            "Rótulos de grupo são categorias ordenadas pelo PIB mediano, sem interpretação de ranking de qualidade de vida.",
            "Não foi realizada previsão, classificação supervisionada ou avaliação de generalização fora destes países.",
        ],
    }
    summary = _json_safe(summary)
    (root / "results" / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    _plots(root, df, x, labels, grid, scores, pca.explained_variance_ratio_)
    return summary


def main() -> None:
    """Disponibilize a execução pelo terminal com diretório de projeto opcional."""
    parser = argparse.ArgumentParser(description="Agrupamento socioeconômico sem rótulos (Opção B).")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Pasta raiz do projeto.")
    args = parser.parse_args()
    summary = run_analysis(args.root)
    selected = summary["selected"]
    print(json.dumps({"selected": selected["config"], "silhouette": selected["metrics"]["silhouette"], "clusters": summary["cluster_counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
