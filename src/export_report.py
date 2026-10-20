"""Gera relatório PDF a partir dos resultados efetivamente executados.

Execute após prepare_data.py e analysis.py: python src/export_report.py
"""
from pathlib import Path
import argparse
import json
from html import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak


def export_report(root: Path) -> Path:
    root = Path(root)
    summary = json.loads((root / "results/summary.json").read_text(encoding="utf-8"))
    grid = pd.read_csv(root / "results/grid_modelos.csv")
    profiles = pd.read_csv(root / "data/processed/perfis.csv")
    font_root = Path("C:/Windows/Fonts")
    if (font_root / "arial.ttf").exists():
        pdfmetrics.registerFont(TTFont("ProjectSans", str(font_root / "arial.ttf")))
        pdfmetrics.registerFont(TTFont("ProjectSans-Bold", str(font_root / "arialbd.ttf")))
        pdfmetrics.registerFontFamily("ProjectSans", normal="ProjectSans", bold="ProjectSans-Bold")
        font = "ProjectSans"
    else:
        font = "Helvetica"
    styles = getSampleStyleSheet()
    for name in ["Normal", "BodyText", "Heading1", "Heading2", "Title"]:
        styles[name].fontName = font
    styles["BodyText"].fontSize = 9.5
    styles["BodyText"].leading = 14
    styles["BodyText"].spaceAfter = 8
    styles["Heading1"].fontSize = 21
    styles["Heading1"].leading = 26
    styles["Heading1"].textColor = colors.HexColor("#133d59")
    styles["Heading1"].spaceAfter = 14
    styles["Heading2"].fontSize = 12
    styles["Heading2"].textColor = colors.HexColor("#2572a3")
    styles["Heading2"].spaceBefore = 8
    styles["Heading2"].spaceAfter = 6
    styles.add(ParagraphStyle("SmallProject", fontName=font, fontSize=8, leading=11, spaceAfter=6))
    styles.add(ParagraphStyle("TableProject", fontName=font, fontSize=8.2, leading=11))
    styles.add(ParagraphStyle("LeadProject", fontName=font, fontSize=13, leading=19, textColor=colors.HexColor("#133d59"), spaceAfter=14))
    story = []
    width = 17 * cm

    def paragraph(text, kind="BodyText"):
        story.append(Paragraph(text, styles[kind]))

    def heading(text):
        paragraph(text, "Heading1")

    def table(rows, widths=None):
        formatted = [[Paragraph(escape(str(cell)), styles["TableProject"]) for cell in row] for row in rows]
        t = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2edf4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#133d59")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#94b4c8")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f9")]),
        ]))
        story.extend([t, Spacer(1, 10)])

    def figure(filename, max_height=8 * cm):
        img = Image(str(root / "figures" / filename))
        ratio = min(width / img.imageWidth, max_height / img.imageHeight)
        img.drawWidth = img.imageWidth * ratio
        img.drawHeight = img.imageHeight * ratio
        story.extend([img, Spacer(1, 7)])

    def page():
        story.append(PageBreak())

    selected = summary["selected"]["metrics"]
    heading("Perfis econômicos em três países")
    paragraph("Brasil, China e Estados Unidos | 2004-2024", "LeadProject")
    paragraph("<b>Opção B - Aprendizado não supervisionado</b><br/>Projeto de Introdução à Ciência de Dados", "BodyText")
    paragraph("<b>Resultado principal.</b> K-Means, Ward e DBSCAN em suas melhores soluções elegíveis produzem a mesma partição de três grupos: um para cada país. Não há transição de grupo ao longo dos 21 anos. A representação escolhida separa sobretudo diferenças nacionais, sem identificar regimes temporais comuns.")
    paragraph("Problema e dados", "Heading2")
    paragraph("Quais perfis de renda, produtividade, estrutura de emprego e distribuição da renda aparecem no painel, e como os países transitam entre eles? Mantemos o tema do projeto original. A unidade é país-ano: 63 linhas, nove indicadores e nenhuma variável-alvo. País e ano são usados apenas na interpretação.")
    table([
        ["Fonte pública", "Indicadores e unidades"],
        ["Banco Mundial", "PIB per capita em US$ constantes de 2015; emprego na agricultura, indústria e serviços (% do emprego total, estimativas OIT)."],
        ["ILOSTAT", "PIB por pessoa ocupada, dólares internacionais constantes de 2021 em PPC; participação da renda do trabalho no PIB (%)."],
        ["WID", "Participações na renda antes de impostos: 50% inferiores, 40% intermediários e 10% superiores. Adultos 20+, divisão igual entre cônjuges."],
    ], [3.3 * cm, 13.7 * cm])
    paragraph("Diagnóstico", "Heading2")
    paragraph("Todos os 63 pares país-ano estão completos, sem duplicatas. As somas das participações são verificadas; diferenças pequenas de arredondamento são corrigidas por fechamento. Códigos de fonte, status e qualidade permanecem nas tabelas congeladas. Arquivos e filtros são rastreados por um manifesto com SHA-256.")
    paragraph("A análise reproduz a fotografia local do projeto; não incorpora revisões online automaticamente. A seleção temporal exclui anos posteriores a 2024 que aparecem em algumas fontes.", "SmallProject")

    page()
    heading("Tratamento e análise exploratória")
    paragraph("A matriz contém sete variáveis: log natural do PIB per capita e da produtividade; participação do trabalho no PIB; duas coordenadas ILR para a composição do emprego; duas para a distribuição da renda. Aplicamos StandardScaler após essas transformações.")
    paragraph("Para uma composição positiva (a, b, c), as coordenadas são ln(a/b)/raiz(2) e raiz(2/3) × ln(raiz(a×b)/c). Isso representa razões entre partes sem incluir três percentuais dependentes. O fechamento corrige arredondamento sem alterar as razões. Cada coordenada recebe escala própria, definindo pesos relativos explícitos na geometria do modelo.")
    paragraph("A imputação de mediana está prevista, com ajuste restrito ao subconjunto de cada experimento. Ela não é acionada nesta base completa. Não removemos extremos apenas por sua magnitude: diferenças econômicas podem ser parte do fenômeno. Não é necessária codificação categórica porque identificadores não entram no modelo.")
    figure("01_eda_series.png", 8.4 * cm)
    paragraph("As séries mostram diferenças persistentes de nível econômico, composição do emprego e distribuição da renda. O PIB per capita em US$ constantes e a produtividade em PPC têm unidades distintas; não calculamos razões entre esses indicadores.", "SmallProject")
    paragraph("Indicadores correlacionados podem ampliar implicitamente o peso de algumas dimensões. Por isso, além da matriz de correlação no notebook, testamos a retirada de conjuntos de variáveis e a troca da regra de escala.")

    page()
    heading("Comparação e seleção dos modelos")
    paragraph("A grade tem 34 configurações: K-Means e Ward com k de 2 a 6; DBSCAN com eps em {0,35; 0,50; 0,65; 0,80; 1; 1,25; 1,50; 2} e min_samples em {3; 4; 5}. K-Means usa 50 inicializações e semente 42. A referência simples é K-Means com k=2.")
    paragraph("Critério do estudo: cobertura de 100%, dois a seis grupos e pelo menos quatro observações por grupo. Entre as soluções elegíveis, maximiza-se silhouette; menor Davies-Bouldin desempata. Calinski-Harabasz complementa a leitura. Esses critérios são escolhas exploratórias, sem confirmação em amostra independente.")
    rows = [["Configuração", "Silhouette", "Davies-Bouldin", "Cobertura", "Menor grupo"]]
    for family, k in [("KMeans", 2), ("KMeans", 3), ("Ward", 3), ("Ward", 5)]:
        r = grid.loc[grid.family.eq(family) & grid.k.eq(k)].iloc[0]
        rows.append([f"{family} k={k}" + (" (inelegível)" if not r.eligible else ""), f"{r.silhouette:.3f}", f"{r.davies_bouldin:.3f}", f"{r.coverage:.0%}", int(r.smallest_cluster)])
    complete_db = grid.loc[grid.family.eq("DBSCAN") & grid.eligible].sort_values(["silhouette", "davies_bouldin"], ascending=[False, True])
    if not complete_db.empty:
        r = complete_db.iloc[0]
        rows.append([f"DBSCAN eps={r.eps:g} / min={int(r.min_samples)}", f"{r.silhouette:.3f}", f"{r.davies_bouldin:.3f}", f"{r.coverage:.0%}", int(r.smallest_cluster)])
    db = summary["dbscan_exploratory"]
    if db:
        r = db["metrics"]
        rows.append([f"DBSCAN eps={db['config']['eps']} / min={db['config']['min_samples']}*", f"{r['silhouette']:.3f}", f"{r['davies_bouldin']:.3f}", f"{r['coverage']:.1%}", r["smallest_cluster"]])
    table(rows, [5.5 * cm, 2.6 * cm, 3.3 * cm, 2.8 * cm, 2.8 * cm])
    paragraph("* DBSCAN calcula as métricas somente nos pontos agrupados quando há ruído. Sua silhouette de 0,912 cobre apenas 19 das 63 observações (44 são ruído), portanto não representa superioridade sobre partições completas. A grade integral permanece disponível.", "SmallProject")
    figure("03_busca_k.png", 5.4 * cm)
    paragraph(f"K-Means k=3: silhouette {selected['silhouette']:.3f}, Davies-Bouldin {selected['davies_bouldin']:.3f}, Calinski-Harabasz {selected['calinski_harabasz']:.2f}. O ganho de silhouette sobre k=2 é {summary['silhouette_gain_vs_baseline']:.3f}. Ward k=3 empata e produz os mesmos grupos; a escolha de K-Means decorre do desempate determinístico. Ward k=5 tem silhouette maior, mas inclui grupo de apenas dois pontos e é inelegível.")

    page()
    heading("Perfis encontrados")
    table([
        ["Grupo / país", "n", "PIB per capita¹", "Trabalho²", "Agro³", "B50⁴", "T10⁴"],
        *[[f"{int(r.cluster)} / {r.countries}", int(r.n_observations), f"{r.gdp_per_capita:,.0f}", f"{r.labor_share:.1f}", f"{r.agriculture:.1f}", f"{r.income_bottom50:.1f}", f"{r.income_top10:.1f}"] for r in profiles.itertuples()],
    ], [3.5 * cm, 1.3 * cm, 3 * cm, 2.5 * cm, 2.1 * cm, 2.3 * cm, 2.3 * cm])
    paragraph("Medianas por grupo. ¹ US$ constantes de 2015; ² % do PIB; ³ % do emprego total; ⁴ % da renda antes de impostos. B50: 50% inferiores; T10: 10% superiores. A numeração segue o PIB per capita mediano e serve apenas para organizar categorias.", "SmallProject")
    figure("04_pca_clusters.png", 8.1 * cm)
    paragraph(f"PCA com duas componentes explica {summary['pca_total_explained_2d']:.1%} da variância. A projeção é apenas visual: os modelos usam sete variáveis. Países aparecem por formas diferentes e grupos por cores.", "SmallProject")
    paragraph("A China combina menor PIB per capita mediano e maior presença do emprego agropecuário. O Brasil apresenta participação elevada dos 10% superiores e participação menor dos 50% inferiores na renda. Os Estados Unidos têm o maior nível de PIB per capita e produtividade entre os casos estudados. Esses contrastes são descrições do painel e não evidência causal ou ranking de bem-estar.")

    page()
    heading("Estabilidade e trajetórias")
    figure("06_trajetorias_clusters.png", 6.4 * cm)
    paragraph("Cada país permanece em seu grupo por todo o período. Os indicadores mudam, mas as mudanças não são suficientes para alterar a partição com a representação e os hiperparâmetros escolhidos.")
    table([["Verificação", "Resultado e alcance"],
           ["18 exclusões temporais", "Retirada de cada bloco de quatro anos nos três países: 51 linhas restantes; tratamento e modelo reajustados. K-Means e Ward: ARI mínimo e médio = 1,000."],
           ["20 sementes de K-Means", "ARI mínimo = 1,000 com 50 inicializações por ajuste."],
           ["Retirada de variáveis", "Retirar composição da renda, retirar PIB/produtividade ou retirar participação do trabalho: ARI = 1,000, com hiperparâmetros fixos."],
           ["RobustScaler", "ARI = 0,663 e silhouette = 0,571: alteração material da partição. A escolha de escala influencia a conclusão."],
          ], [4 * cm, 13 * cm])
    paragraph("ARI compara partições nas mesmas linhas; não mede acurácia ou qualidade econômica. Para DBSCAN, ruído é incluído como categoria no ARI, com cobertura registrada separadamente. Os blocos temporais se sobrepõem: os 18 valores não são amostras independentes e não geram intervalos de confiança.")
    paragraph("As sensibilidades mantêm a configuração selecionada. Elas não refazem toda a seleção de modelos; suas silhouettes são calculadas em espaços diferentes e não compõem um ranking direto. A estabilidade temporal, portanto, não elimina a dependência da representação.")

    page()
    heading("Conclusões, limites e reprodução")
    paragraph("A pergunta foi respondida com três perfis persistentes, correspondentes aos países. A conclusão útil é que o painel contém diferenças nacionais fortes nas dimensões escolhidas. Não encontramos evidência de transições entre regimes compartilhados com essa parametrização. A concordância entre K-Means e Ward e a estabilidade por blocos apoiam a consistência interna, enquanto a troca de escala revela uma limitação concreta.")
    paragraph("Limitações e próximos passos", "Heading2")
    paragraph("Apenas três países e 21 anos impedem generalização mundial. Anos consecutivos são dependentes; métricas internas não comprovam grupos naturais. Fontes secundárias contêm estimativas modeladas ou imputadas, com revisões futuras possíveis. A OIT recomenda cautela em comparações com esses dados. O estudo não estabelece causas e não deve fundamentar decisões sem investigação adicional.")
    paragraph("Como extensão, ampliar os países com variáveis comparáveis e cobertura temporal comum; testar outras definições econômicas e pesos por domínio; investigar subperíodos dentro de cada país. Os grupos atuais ajudam a selecionar casos e formular hipóteses, sem substituir análise econômica contextual.")
    paragraph("Execução e arquivos", "Heading2")
    paragraph("Use Python 3.12, instale requirements.txt e execute src/prepare_data.py, src/analysis.py e src/export_report.py, nessa ordem. O notebook projeto_nao_supervisionado.ipynb reproduz o tratamento e a análise e já contém saídas reais. Os pequenos recortes de dados acompanham o projeto; a reprodução padrão é offline. A nova extração das fontes locais é opcional e está documentada no README.")
    paragraph("Referências primárias", "Heading2")
    for title, url in [
        ("Banco Mundial - PIB per capita", "https://data.worldbank.org/indicator/NY.GDP.PCAP.KD"),
        ("Banco Mundial - emprego na agricultura", "https://data.worldbank.org/indicator/SL.AGR.EMPL.ZS"),
        ("OIT - ILOSTAT", "https://ilostat.ilo.org/data/"),
        ("OIT - nota sobre comparações", "https://www.ilo.org/resource/news/note-ilo-modelled-estimates-and-country-rankings-or-comparisons"),
        ("WID - metodologia", "https://wid.world/methodology/"),
        ("scikit-learn - clustering e métricas", "https://scikit-learn.org/stable/modules/clustering.html"),
    ]:
        paragraph(f'<link href="{url}" color="#2572a3">{escape(title)}</link>', "SmallProject")
    paragraph("Entrega: link do repositório público no GitHub e link do vídeo gravado pelo estudante. O roteiro em docs/roteiro_video.md acompanha os resultados deste relatório.", "SmallProject")

    target = root / "docs/relatorio.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c5d4df"))
        canvas.line(2 * cm, 1.6 * cm, 19 * cm, 1.6 * cm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#5e7180"))
        canvas.drawString(2 * cm, 1.1 * cm, "Introdução à Ciência de Dados | Opção B | Dados 2004-2024")
        canvas.drawRightString(19 * cm, 1.1 * cm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(target), pagesize=(21 * cm, 29.7 * cm),
                            rightMargin=2 * cm, leftMargin=2 * cm, topMargin=1.9 * cm, bottomMargin=2.1 * cm,
                            title="Perfis econômicos de Brasil, China e Estados Unidos - Aprendizado não supervisionado",
                            author="Projeto de Introdução à Ciência de Dados")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(export_report(parser.parse_args().root))
