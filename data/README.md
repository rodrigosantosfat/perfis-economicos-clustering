# Dados e proveniência

## Recorte incluído

O projeto usa **Brasil (BRA), China (CHN) e Estados Unidos (USA)** nos anos **2004–2024**, com 63 país-anos e nove indicadores. Os dados públicos foram selecionados dos arquivos locais fornecidos pelo autor; a reprodução habitual usa somente este recorte, sem acesso à pasta original ou atualização online.

| Coluna no painel | Definição e unidade | Fonte/código |
|---|---|---|
| `country`, `year` | Código ISO3 e ano; identificadores, excluídos dos atributos do modelo | Chave da integração |
| `gdp_per_capita` | PIB per capita em **US$ constantes de 2015**; não é uma medida em PPC | Banco Mundial, `NY.GDP.PCAP.KD` |
| `productivity` | PIB por pessoa ocupada em dólares internacionais constantes de 2021, PPC | ILOSTAT, `GDP_211P_NOC_NB` |
| `labor_share` | Participação da renda do trabalho no PIB, em % | ILOSTAT, `SDG_1041_NOC_RT` |
| `agriculture` | Emprego na agropecuária como % do emprego total | Banco Mundial/ILOSTAT, `SL.AGR.EMPL.ZS` |
| `industry` | Emprego na indústria como % do emprego total | Banco Mundial/ILOSTAT, `SL.IND.EMPL.ZS` |
| `services` | Emprego nos serviços como % do emprego total | Banco Mundial/ILOSTAT, `SL.SRV.EMPL.ZS` |
| `income_bottom50` | Participação dos 50% inferiores na renda nacional antes de impostos, em % | WID, `sptincj992`, `p0p50` |
| `income_middle40` | Participação dos 40% intermediários na mesma renda, em % | WID, `sptincj992`, `p50p90` |
| `income_top10` | Participação dos 10% superiores na mesma renda, em % | WID, `sptincj992`, `p90p100` |


Na WID, `sptincj992` identifica participação da renda nacional pré-tributação para adultos acima de 20 anos, com recursos igualmente divididos dentro do casal. As três frações foram convertidas em porcentagens. As definições e referências específicas de BR, CN e US estão em `raw/wid_metadata.csv`.

O PIB per capita é medido em **US$ constantes de 2015** e a produtividade em **PPC de 2021**: não são unidades intercambiáveis. Setores representam emprego, não produção. O campo `labor_share` não é participação de um percentil da população: é uma participação funcional do trabalho no PIB.

## Arquivos congelados

| Arquivo em raw/ | Linhas de dados | Metadados |
|---|---|---|
| ilostat.csv | 126 | Não |
| wb_gdp.csv | 63 | Não |
| wb_gdp_metadata.csv | 1 | Sim |
| wb_sectors.csv | 189 | Não |
| wid_income.csv | 189 | Não |
| wid_metadata.csv | 3 | Sim |

`raw/painel_fontes.csv` é reconstruído por `src/prepare_data.py`, com uma linha por país-ano. `raw/manifest.json` registra extração UTC, período, países, nomes e hashes SHA-256 dos arquivos originais e das tabelas congeladas. Os hashes das fontes congeladas são verificados antes da integração. Os arquivos ILO originais trazem `20260919T1910` no nome; a extração deste recorte ocorreu em 20/10/2026. Não se assume que todas as fontes possuam a mesma data de atualização.

## Regras da integração

1. Filtrar países, anos, códigos e percentis especificados no dicionário.
2. Verificar a unicidade das chaves país-ano-indicador antes de pivotar.
3. Integrar por país-ano e exigir os 63 registros esperados e nove indicadores.
4. Confirmar ausência de faltantes, valores monetários positivos, participações válidas e fechamento aproximado a 100% das composições.
5. Preservar `source`, `indicator` e `obs_status` do ILOSTAT para auditoria, sem convertê-los em atributos.

O recorte completo não exigiu imputação. O script de modelagem dispõe de imputação por mediana caso necessário em suas operações de ajuste; sua presença não significa que foram inventados dados nesta execução. Não se criou rótulo-alvo a partir de país, ano ou renda.

## Qualidade e incerteza

Para `labor_share`, a tabela congelada contém 18 flags vazias, 42 `I` e 3 `M`; para produtividade, as 63 flags estão vazias. Os códigos foram preservados e não decodificados sem o dicionário confirmado da edição original. Uma flag vazia não implica dado diretamente observado. Os nomes dos indicadores setoriais os identificam como estimativas modeladas da OIT. As [orientações da OIT](https://www.ilo.org/resource/news/note-ilo-modelled-estimates-and-country-rankings-or-comparisons) devem ser consideradas na interpretação; este trabalho não usa agrupamentos para produzir ranking nacional.

As fontes podem revisar anos anteriores e combinam metodologias distintas. Os resultados referem-se a esta fotografia local, sem propagação de incerteza dos indicadores. A existência de dados para todos os anos não equivale a observações independentes ou medidas sem erro.

## Dados processados

- `processed/painel_clusters.csv`: nove indicadores, categoria de grupo e coordenadas PCA para cada país-ano.
- `processed/transformed.csv`: sete atributos transformados, respectivas versões padronizadas (`z_...`) e categoria de grupo.
- `processed/perfis.csv`: número de observações, países e medianas de atributos originais/padronizados por grupo.

Grupo é uma saída do algoritmo e não uma classe verdadeira. PCA é apenas projeção visual. Os números dos grupos são ordenados pelo PIB mediano para facilitar a leitura e não representam uma escala de qualidade de vida.

## Referências

- Banco Mundial: [PIB per capita em US$ constantes de 2015 — NY.GDP.PCAP.KD](https://data.worldbank.org/indicator/NY.GDP.PCAP.KD).
- Banco Mundial/ILOSTAT: [emprego na agropecuária — SL.AGR.EMPL.ZS](https://data.worldbank.org/indicator/SL.AGR.EMPL.ZS), [indústria — SL.IND.EMPL.ZS](https://data.worldbank.org/indicator/SL.IND.EMPL.ZS) e [serviços — SL.SRV.EMPL.ZS](https://data.worldbank.org/indicator/SL.SRV.EMPL.ZS).
- OIT/ILOSTAT: [portal de dados](https://ilostat.ilo.org/data/) e [orientações sobre estimativas modeladas e comparações entre países](https://www.ilo.org/resource/news/note-ilo-modelled-estimates-and-country-rankings-or-comparisons).
- World Inequality Database: [metodologia e recursos DINA](https://wid.world/methodology/). As definições específicas da variável `sptincj992` e as referências de cada país estão preservadas em `data/raw/wid_metadata.csv`.
- scikit-learn: [agrupamento e avaliação](https://scikit-learn.org/stable/modules/clustering.html), [KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html), [Ward](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.AgglomerativeClustering.html), [DBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html), [StandardScaler](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html) e [PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html).


Consulta: 20/10/2026. Consulte os termos e as condições dos provedores ao reutilizar dados e mantenha as atribuições das fontes. Este repositório distribui o recorte necessário ao estudo e os metadados; não reivindica autoria dos indicadores.
