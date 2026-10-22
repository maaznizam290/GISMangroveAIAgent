# Indus Delta mangrove study: GIS handover (landsat 2026)

Handover status: **INCOMPLETE** (see `handover_validation.md`).

Missing required deliverables:

* composite_dry
* composite_post_monsoon
* landcover
* classification_uncertainty
* mangrove
* tidal_inundation
* soil_salinity_proxy
* freshwater_influence_proxy
* training_samples
* validation_samples
* candidate_plots
* site_a
* site_b
* site_alternatives
* annual_metrics
* site_metrics
* classification_accuracy
* candidate_site_scores
* confusion_matrix
* selection_criteria
* site_comparison
* accuracy_report
* selection_report
* preview_quicklook
* model_metadata
* qgis_project

## Contents

* `rasters/`: Cloud Optimized GeoTIFFs in EPSG:32642, at the native grid of their source
  (never upsampled). Band names, units, nodata, layer type, validation status and source are
  stored in each file.
* `vectors/indus_delta_handover.gpkg`: AOI, reference point, samples, candidate plots, Site A,
  Site B and alternatives, reference water layers (EPSG:32642).
* `tables/`: annual_metrics, site_metrics, classification_accuracy, image_inventory,
  candidate_site_scores and supporting tables.
* `qgis/indus_delta_handover.qgz`: QGIS project (relative paths), with the "Handover overview"
  print layout (map, legend, scale bar, source notes). `handover_layout.png` is a preview.
* `docs/`: methods report, data dictionary, limitations, processing history, software
  versions, study protocol, uncertainty guide, AOI review and run reports.
* `config/`: the configuration used.
* `handover_manifest.json`: SHA-256 of every file.

Open the package by double-clicking `qgis/indus_delta_handover.qgz` in QGIS 3.34 or later.
