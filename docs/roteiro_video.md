# Roteiro sugerido para o vídeo

**Duração sugerida:** 6–8 minutos. Use o notebook e as figuras como apoio e adapte a fala ao seu jeito. O vídeo é a segunda entrega e será gravado pelo autor.

## 0:00–0:45 — Problema e abordagem

Mostre o título e a pergunta do README.

“Meu projeto escolheu a opção B, aprendizado não supervisionado. Investiguei quais perfis aparecem ao combinar economia, emprego e distribuição da renda no Brasil, na China e nos Estados Unidos entre 2004 e 2024. A unidade é país-ano. Quero explorar semelhanças, e não prever uma variável-alvo. País e ano não foram usados como atributos dos modelos.”

## 0:45–1:35 — Fontes e dados

Mostre `data/README.md` e as primeiras linhas do painel.

“Integrei dados públicos do Banco Mundial, ILOSTAT e WID. O painel tem 63 observações e nove indicadores, sem duplicatas ou valores faltantes no recorte. Os dados congelados e seus metadados estão no repositório. O PIB per capita usa US$ constantes de 2015; produtividade usa PPC de 2021. As participações setoriais representam emprego. A renda da WID é antes dos impostos, para adultos com divisão de recursos dentro do casal.”

## 1:35–2:25 — EDA e tratamento

Mostre `01_eda_series.png` e `02_correlacao_features.png`.

“Verifiquei unidades, tipos, duplicatas, intervalos e totais das composições. Usei logaritmo no PIB e na produtividade para expressar diferenças relativas. Emprego e renda têm três partes que somam 100%; por isso, transformei cada composição em duas coordenadas ILR, que representam razões entre as partes. Depois padronizei os sete atributos. A imputação por mediana existe no pipeline, mas não foi necessária nesta fotografia completa.”

## 2:25–3:25 — Comparação de técnicas

Mostre `03_busca_k.png` e a tabela de comparação do relatório.

“Comparei KMeans e Ward de dois a seis grupos, além de 24 parametrizações de DBSCAN. No total são 34 configurações. A regra foi escolher a maior silhouette entre partições com cobertura integral, dois a seis grupos e pelo menos quatro observações em cada grupo; no empate, usei Davies–Bouldin. Também reportei Calinski–Harabasz e cobertura. O escolhido foi KMeans (k=3), com silhouette 0,668. A referência simples KMeans com dois grupos teve 0,544.”

Se comentar DBSCAN, leia a cobertura junto da silhouette: Entre as parametrizações exploratórias de DBSCAN com métricas definidas, DBSCAN (eps=0,35, min_samples=5) obteve silhouette 0,912, com cobertura de 30,2% e 44 observações de ruído. Essa silhouette usa apenas os pontos agrupados quando há ruído; por isso, ela deve ser lida junto da cobertura, sem comparação direta com partições completas.

## 3:25–4:40 — Resultados e perfis

Mostre `04_pca_clusters.png`, `05_perfis_heatmap.png` e `06_trajetorias_clusters.png`.

“Os grupos foram calculados usando os sete atributos. A PCA só permite visualizar em duas dimensões, que retêm 89,0% da variância. Os números dos grupos são categorias ordenadas pelo PIB mediano para facilitar a leitura; não são ranking de qualidade de vida.”

“O principal resultado foi a separação dos países: os 21 anos da China ficaram no grupo 1, os 21 do Brasil no grupo 2 e os 21 dos Estados Unidos no grupo 3. Portanto, diferenças persistentes entre países dominaram as mudanças ao longo do período. Não encontrei transições temporais na partição escolhida. As melhores configurações das três técnicas chegaram à mesma partição.”

Escolha dois perfis da tabela a seguir para explicar com suas palavras. Cite a composição do emprego e da renda, além do nível econômico; evite atribuir o resultado a uma política específica.

| Grupo | n | Países | PIB/hab. US$2015 | PIB/ocup. PPC2021 | Renda do trabalho % | Renda dos 10% % |
|---|---|---|---|---|---|---|
| 1 | 21 | CHN | 7.686 | 25.450 | 51,4 | 42,7 |
| 2 | 21 | BRA | 8.771 | 40.241 | 58,4 | 58,8 |
| 3 | 21 | USA | 55.665 | 131.690 | 58,5 | 45,4 |

| País | Grupo 1 | Grupo 2 | Grupo 3 |
|---|---|---|---|
| Brasil | 0 | 21 | 0 |
| China | 21 | 0 | 0 |
| Estados Unidos | 0 | 0 | 21 |

Não houve mudança de grupo entre anos consecutivos neste ajuste.

## 4:40–5:50 — Robustez

Mostre as tabelas de robustez e sensibilidade no relatório.

“Como os anos de um país são dependentes, retirei blocos de quatro anos de todos os países ao mesmo tempo. Reajustei o pré-processamento e o modelo nos 51 país-anos restantes e comparei as partições com ARI. Foram 18 blocos. Para a técnica selecionada, o ARI médio foi 1,000 e o mínimo foi 1,000. Também testei 20 sementes de KMeans e mudanças de atributos e de escala. O ARI mede estabilidade entre partições; não é acurácia contra rótulos verdadeiros.”

O cenário com menor concordância foi Completo + RobustScaler: ARI 0,663. Explique que a escolha das variáveis influencia os grupos.

## 5:50–6:45 — Conclusão e limites

“O estudo encontrou uma forma reprodutível de resumir estes perfis econômicos. Ele pode ajudar a escolher comparações e hipóteses para novos estudos. A base é pequena, tem três países e contém estimativas sujeitas a revisão. A OIT alerta para a incerteza das observações modeladas. Os grupos não são causas, não são ranking e não permitem generalizar para outros países. O código, os dados usados, os resultados e as instruções de execução estão no repositório.”

## Antes de publicar

- Execute ou abra o notebook para mostrar resultados reais.
- Confira se texto e figuras estão legíveis na gravação e se o áudio está claro.
- Publique o vídeo com acesso permitido ao professor e teste o link.
- Envie no Classroom o link do repositório **público** e o link do vídeo. Não é necessário gravar uma segunda abordagem supervisionada.
