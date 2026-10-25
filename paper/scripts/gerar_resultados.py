#!/usr/bin/python3
"""Valida o resultado SQL, gera tabelas e exporta mapa/layout com PyQGIS.

Executar na raiz do repositorio:
  QT_QPA_PLATFORM=offscreen /usr/bin/python3 paper/scripts/gerar_resultados.py
Nao abre conexoes com o banco.
"""
import csv
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFillSymbol, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemMap,
    QgsLayoutItemScaleBar, QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize,
    QgsPrintLayout, QgsProject, QgsRectangle, QgsReferencedRectangle,
    QgsRuleBasedRenderer, QgsVectorLayer,
)
from qgis.PyQt.QtGui import QFont

PAPER = Path(__file__).resolve().parents[1]
OUT = PAPER / "resultados"


def br(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def tex(text):
    return "".join({"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#"}.get(c, c)
                   for c in str(text))


def validate(data):
    rows = [f["properties"] for f in data["bairros"]["features"]]
    checks, summary = data["validacao"], data["resumo"]
    for key in ("ids_nulos", "ids_repetidos", "pontos_fora", "pontos_ambiguos",
                "geometrias_descartadas", "bairros_invalidos", "bairros_sem_geom"):
        if checks[key] != 0:
            raise ValueError(f"Reavaliar diagnostico: {key}={checks[key]}")
    assert len(rows) == checks["bairros"] == checks["bairros_ids_distintos"] == 75
    assert len({r["gid"] for r in rows}) == len(rows)
    for r in rows:
        assert math.isfinite(r["area_km2"]) and r["area_km2"] > 0
        assert 0 <= r["n_100"] <= r["n_250"] <= r["n_500"] <= r["n_social"]
        for radius in (100, 250, 500):
            pct = r[f"pct_{radius}"]
            if r["n_social"] == 0:
                assert pct is None
            else:
                assert pct is not None and 0 <= pct <= 100
                assert abs(pct - 100 * r[f"n_{radius}"] / r["n_social"]) <= 0.00501
        for category, column in (("social", "n_social"), ("luz", "n_luz")):
            assert math.isclose(r[f"dens_{category}"], r[column] / r["area_km2"], abs_tol=1e-9)
    totals = {r["categoria"]: r for r in summary["cobertura"]}
    assert sum(r["n_social"] for r in rows) == totals["social"]["com_geom"]
    assert sum(r["n_luz"] for r in rows) == totals["iluminacao"]["com_geom"]
    assert sum(r["n_social"] > 0 for r in rows) == summary["bairros_com_social"]
    for s in summary["sensibilidade"]:
        assert sum(r[f'n_{s["raio"]}'] for r in rows) == s["proximos"]
        assert sum(r["n_social"] for r in rows) == s["total"]
        assert abs(s["pct"] - 100 * s["proximos"] / s["total"]) <= 0.00501
    return rows


def export_tables(data, rows):
    (OUT / "bairros.geojson").write_text(
        json.dumps(data["bairros"], ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {k: v for k, v in data.items() if k != "bairros"}
    (OUT / "resumo.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    fields = ["gid", "nome", "area_km2", "n_social", "n_luz", "dens_social", "dens_luz",
              "n_100", "n_250", "n_500", "pct_100", "pct_250", "pct_500"]
    with (OUT / "indicadores.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["gid"]))
    top = sorted(rows, key=lambda r: (-r["n_social"], r["gid"]))[:5]
    lines = ["% Gerado de analise.json; nao editar manualmente.",
             r"\begin{tabular}{lrrrrr}", r"\toprule",
             r"Bairro & $S_b$ & $L_b$ & $D_S$ & $D_L$ & $P_b(500)$ (\%) \\",
             r"\midrule"]
    for r in top:
        lines.append(" & ".join([
            tex(r["nome"].title()), str(r["n_social"]), str(r["n_luz"]),
            br(r["dens_social"], 2), br(r["dens_luz"], 2), br(r["pct_500"], 2),
        ]) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (OUT / "top5.tex").write_text("\n".join(lines) + "\n")


CLASSES = [
    ("{f} IS NULL", "Sem registros sociais", "#d9dde3"),
    ("{f} = 0", "0%", "#ffffff"),
    ("{f} > 0 AND {f} <= 25", ">0–25%", "#d6e6f4"),
    ("{f} > 25 AND {f} <= 50", ">25–50%", "#94bddd"),
    ("{f} > 50 AND {f} <= 75", ">50–75%", "#488ac1"),
    ("{f} > 75", ">75–100%", "#154c79"),
]


def symbol(color):
    return QgsFillSymbol.createSimple({
        "color": color, "outline_color": "#555e68", "outline_width": "0.13",
        "outline_width_unit": "MM", "joinstyle": "round",
    })


def label(layout, text, x, y, w, h, size=8, bold=False):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    font = QFont("DejaVu Sans")
    font.setPointSizeF(size)
    font.setBold(bold)
    item.setFont(font)
    item.setMargin(0)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y))
    item.attemptResize(QgsLayoutSize(w, h))
    return item


def render(data):
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:31982"))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle("156: abordagem social e manutencao da iluminacao, 2017–2018")
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("Comparacao 100 e 500 metros")
    layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(150, 93))
    layers = []
    for index, radius in enumerate((100, 500)):
        layer = QgsVectorLayer(str(OUT / "bairros.geojson"), f"Proximidade a {radius} m", "ogr")
        assert layer.isValid() and layer.featureCount() == 75
        assert layer.crs().authid() == "EPSG:4326"
        assert all(f.geometry().isGeosValid() for f in layer.getFeatures())
        root = QgsRuleBasedRenderer.Rule(None)
        for expr, text, color in CLASSES:
            root.appendChild(QgsRuleBasedRenderer.Rule(
                symbol(color), filterExp=expr.format(f=f'"pct_{radius}"'), label=text))
        layer.setRenderer(QgsRuleBasedRenderer(root))
        project.addMapLayer(layer)
        layers.append(layer)
        trans = QgsCoordinateTransform(layer.crs(), project.crs(), project)
        extent = trans.transformBoundingBox(layer.extent())
        extent.scale(1.06)
        map_item = QgsLayoutItemMap(layout)
        map_item.setCrs(project.crs())
        layout.addLayoutItem(map_item)
        x = 1 + 76 * index
        map_item.attemptMove(QgsLayoutPoint(x, 10))
        map_item.attemptResize(QgsLayoutSize(72, 60))
        map_item.setLayers([layer])
        map_item.setKeepLayerSet(True)
        map_item.zoomToExtent(QgsRectangle(extent))
        s = next(s for s in data["resumo"]["sensibilidade"] if s["raio"] == radius)
        label(layout, f"({'ab'[index]}) Raio de {radius} m", x, 0, 72, 4.5, 9, True)
        label(layout, f'{s["proximos"]}/{s["total"]} registros · {br(s["pct"], 2)}%',
              x, 5, 72, 4, 7.5)
        label(layout, "N\n↑", x + 64, 12, 7, 10, 9, True)
        scale = QgsLayoutItemScaleBar(layout)
        scale.setStyle("Single Box")
        scale.setLinkedMap(map_item)
        scale.setUnits(Qgis.DistanceUnit.Kilometers)
        scale.setUnitsPerSegment(5)
        scale.setNumberOfSegments(2)
        scale.setNumberOfSegmentsLeft(0)
        scale.setUnitLabel("km")
        scale.setFont(QFont("DejaVu Sans", 7))
        scale.setHeight(1)
        layout.addLayoutItem(scale)
        scale.attemptMove(QgsLayoutPoint(x + 18, 69))
    for index, (_, text, color) in enumerate(CLASSES):
        x, y = 1 + (index % 3) * 50, 78 + (index // 3) * 5.5
        box = QgsLayoutItemShape(layout)
        box.setShapeType(QgsLayoutItemShape.Rectangle)
        box.setSymbol(symbol(color))
        layout.addLayoutItem(box)
        box.attemptMove(QgsLayoutPoint(x, y))
        box.attemptResize(QgsLayoutSize(4, 3))
        label(layout, text, x + 5.5, y - 0.5, 44, 4, 7)
    label(layout, "Fonte: Postgiscwb (156 e limites de bairros). 2017–2018. Calculo em EPSG:31982.",
          1, 89, 148, 3, 6)
    project.layoutManager().addLayout(layout)
    project.layerTreeRoot().findLayer(layers[0].id()).setItemVisibilityChecked(False)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, project.crs()))
    assert project.write(str(OUT / "analise_gis.qgz"))
    exporter = QgsLayoutExporter(layout)
    pdf = QgsLayoutExporter.PdfExportSettings()
    pdf.forceVectorOutput = True
    assert exporter.exportToPdf(str(OUT / "mapa_gis.pdf"), pdf) == QgsLayoutExporter.Success
    preview = exporter.renderPageToImage(0, dpi=200)
    assert not preview.isNull() and preview.save(str(OUT / "mapa_gis.png"), "PNG")
    print("Mapa e projeto QGIS exportados; QGIS", Qgis.QGIS_VERSION)


if __name__ == "__main__":
    data = json.loads((OUT / "analise.json").read_text())
    rows = validate(data)
    export_tables(data, rows)
    with TemporaryDirectory(prefix="bd2-qgis-") as auth_dir:
        os.environ["QGIS_AUTH_DB_DIR_PATH"] = auth_dir
        render(data)
    print(f"Validacao concluida: {len(rows)} bairros, "
          f'{sum(r["n_social"] for r in rows)} registros sociais, '
          f'{sum(r["n_luz"] for r in rows)} registros de iluminacao.')
