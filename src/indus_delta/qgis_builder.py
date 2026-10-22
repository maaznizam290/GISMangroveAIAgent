"""Build and validate the QGIS handover project with PyQGIS.

Standalone script: it runs under a Python that has QGIS (e.g. Ubuntu `python3-qgis`), not
in the project environment, so it imports nothing from indus_delta.

    QT_QPA_PLATFORM=offscreen python3.12 qgis_builder.py spec.json

The spec (written by indus_delta.handover) lists layers with paths, groups, styles and source
notes. The script writes the project with relative paths, exports the overview layout to PNG,
then reopens the saved project in a clean session and records what it found in the result
JSON named in the spec.
"""

from __future__ import annotations

import json
import sys
import traceback

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsColorRampShader,
    QgsContrastEnhancement,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMultiBandColorRenderer,
    QgsPalettedRasterRenderer,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor, QFont


def qgis_colour(value: str) -> str:
    """'#rrggbb' or '#rrggbbaa' -> 'r,g,b,a' (QGIS reads 8-digit hex as #aarrggbb)."""
    if value in (None, "none"):
        return "0,0,0,0"
    h = value.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return f"{r},{g},{b},{a}"


def style_raster(layer: QgsRasterLayer, style: dict) -> None:
    kind = style.get("type", "default")
    provider = layer.dataProvider()
    if kind == "paletted":
        classes = [
            QgsPalettedRasterRenderer.Class(c["value"], QColor(c["color"]), c["label"])
            for c in style["classes"]
        ]
        layer.setRenderer(QgsPalettedRasterRenderer(provider, style.get("band", 1), classes))
    elif kind == "pseudocolor":
        ramp = QgsColorRampShader(style["min"], style["max"])
        ramp.setColorRampType(QgsColorRampShader.Interpolated)
        n = len(style["colors"])
        items = []
        for i, c in enumerate(style["colors"]):
            v = style["min"] + (style["max"] - style["min"]) * i / max(n - 1, 1)
            items.append(QgsColorRampShader.ColorRampItem(v, QColor(c), f"{v:g}"))
        ramp.setColorRampItemList(items)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(ramp)
        renderer = QgsSingleBandPseudoColorRenderer(provider, style.get("band", 1), shader)
        renderer.setClassificationMin(style["min"])
        renderer.setClassificationMax(style["max"])
        layer.setRenderer(renderer)
    elif kind == "rgb":
        renderer = QgsMultiBandColorRenderer(provider, style["red"], style["green"], style["blue"])
        for band, setter in (
            (style["red"], renderer.setRedContrastEnhancement),
            (style["green"], renderer.setGreenContrastEnhancement),
            (style["blue"], renderer.setBlueContrastEnhancement),
        ):
            ce = QgsContrastEnhancement(provider.dataType(band))
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            ce.setMinimumValue(style.get("min", 0.0))
            ce.setMaximumValue(style.get("max", 0.3))
            setter(ce)
        layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_vector(layer: QgsVectorLayer, style: dict) -> None:
    kind = style.get("type")
    if kind == "fill":
        sym = QgsFillSymbol.createSimple(
            {
                "color": style.get("fill", "0,0,0,0"),
                "style": "no" if style.get("fill") in (None, "none") else "solid",
                "outline_color": style.get("outline", "#000000"),
                "outline_width": str(style.get("width", 0.5)),
                "outline_style": style.get("outline_style", "solid"),
            }
        )
    elif kind == "line":
        sym = QgsLineSymbol.createSimple(
            {"color": style.get("color", "#000000"), "width": str(style.get("width", 0.6))}
        )
    elif kind == "marker":
        sym = QgsMarkerSymbol.createSimple(
            {
                "name": style.get("shape", "circle"),
                "color": style.get("color", "#000000"),
                "size": str(style.get("size", 2.0)),
            }
        )
    else:
        return
    layer.setRenderer(QgsSingleSymbolRenderer(sym))


def build(spec: dict) -> dict:
    project = QgsProject.instance()
    project.clear()
    crs = QgsCoordinateReferenceSystem(spec["crs"])
    project.setCrs(crs)
    project.setTitle(spec["title"])
    project.writeEntryBool("Paths", "/Absolute", False)
    root = project.layerTreeRoot()
    added, problems = [], []
    # Groups in the order given; layers inside a group in the order given (first on top).
    for group_name in spec["groups"]:
        root.addGroup(group_name)
    for item in spec["layers"]:
        if item["kind"] == "raster":
            layer = QgsRasterLayer(item["path"], item["name"], "gdal")
        else:
            layer = QgsVectorLayer(item["path"], item["name"], "ogr")
        if not layer.isValid():
            problems.append(f"{item['name']}: could not load {item['path']}")
            continue
        (style_raster if item["kind"] == "raster" else style_vector)(layer, item.get("style", {}))
        md = layer.metadata()
        md.setAbstract(item.get("source_note", ""))
        layer.setMetadata(md)
        project.addMapLayer(layer, False)
        node = root.findGroup(item["group"]).addLayer(layer)
        node.setItemVisibilityChecked(item.get("visible", True))
        added.append(item["name"])

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(spec["layout"]["name"])
    page = layout.pageCollection().page(0)
    page.setPageSize("A4", page.Orientation.Landscape)
    title = QgsLayoutItemLabel(layout)
    title.setText(spec["layout"]["title"])
    title.setFont(QFont("Arial", 14))
    title.attemptMove(QgsLayoutPoint(10, 6, QgsUnitTypes.LayoutMillimeters))
    title.attemptResize(QgsLayoutSize(277, 10, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(title)
    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(10, 18, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(190, 160, QgsUnitTypes.LayoutMillimeters))
    map_item.setCrs(crs)
    extent_layers = [project.mapLayersByName(n) for n in spec["layout"]["extent_layers"]]
    extent_layers = [lyr[0] for lyr in extent_layers if lyr]
    if extent_layers:
        ext = extent_layers[0].extent()
        for lyr in extent_layers[1:]:
            ext.combineExtentWith(lyr.extent())
        ext.scale(1.05)
        # zoomToExtent keeps the frame size (setExtent would resize the frame to the extent).
        map_item.zoomToExtent(ext)
    map_item.setFrameEnabled(True)
    layout.addLayoutItem(map_item)
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legend")
    legend.setLinkedMap(map_item)
    legend.attemptMove(QgsLayoutPoint(205, 18, QgsUnitTypes.LayoutMillimeters))
    for style_key, size in (
        (QgsLegendStyle.Title, 11),
        (QgsLegendStyle.Group, 9),
        (QgsLegendStyle.Subgroup, 8),
        (QgsLegendStyle.SymbolLabel, 7),
    ):
        fmt = legend.rstyle(style_key).textFormat()
        fmt.setSize(size)
        legend.rstyle(style_key).setTextFormat(fmt)
    legend.setWrapString("_")
    # Only layers drawn in the map appear in the legend (hidden context layers do not).
    legend.setLegendFilterByMapEnabled(True)
    layout.addLayoutItem(legend)
    scalebar = QgsLayoutItemScaleBar(layout)
    scalebar.setStyle("Single Box")
    scalebar.setLinkedMap(map_item)
    scalebar.setUnits(Qgis.DistanceUnit.Kilometers)
    scalebar.setUnitLabel("km")
    scalebar.setNumberOfSegments(4)
    scalebar.setNumberOfSegmentsLeft(0)
    scalebar.setUnitsPerSegment(spec["layout"].get("scalebar_segment_km", 1.0))
    scalebar.attemptMove(QgsLayoutPoint(12, 180, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(scalebar)
    notes = QgsLayoutItemLabel(layout)
    notes.setText(spec["layout"]["notes"])
    notes.setFont(QFont("Arial", 6))
    notes.attemptMove(QgsLayoutPoint(10, 192, QgsUnitTypes.LayoutMillimeters))
    notes.attemptResize(QgsLayoutSize(277, 14, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(notes)
    project.layoutManager().addLayout(layout)

    if not project.write(spec["project_path"]):
        problems.append(f"project.write failed: {project.error()}")
    png_status = QgsLayoutExporter(layout).exportToImage(
        spec["layout_png"], QgsLayoutExporter.ImageExportSettings()
    )
    if png_status != QgsLayoutExporter.Success:
        problems.append(f"layout PNG export failed with status {png_status}")
    return {"added": added, "problems": problems}


def validate(spec: dict) -> dict:
    """Reopen the saved project in a clean state and report what loads."""
    project = QgsProject.instance()
    project.clear()
    ok = project.read(spec["project_path"])
    layers = list(project.mapLayers().values())
    layout = project.layoutManager().layoutByName(spec["layout"]["name"])
    item_types = sorted({type(i).__name__ for i in layout.items()}) if layout else []
    return {
        "read_ok": bool(ok),
        "project_crs": project.crs().authid(),
        "absolute_paths": project.readBoolEntry("Paths", "/Absolute", False)[0],
        "layers": [
            {
                "name": lyr.name(),
                "valid": lyr.isValid(),
                "crs": lyr.crs().authid(),
                "source": lyr.source(),
            }
            for lyr in layers
        ],
        "groups": [g.name() for g in project.layerTreeRoot().findGroups()],
        "layout_found": layout is not None,
        "layout_item_types": item_types,
    }


def main(spec_path: str) -> int:
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    app = QgsApplication([], False)
    app.initQgis()
    result = {"qgis_version": Qgis.version()}
    try:
        result["build"] = build(spec)
        result["validation"] = validate(spec)
    except Exception:  # report every failure to the caller instead of crashing silently
        result["error"] = traceback.format_exc()
    finally:
        with open(spec["result_path"], "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        app.exitQgis()
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
