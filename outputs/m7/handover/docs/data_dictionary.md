# Data dictionary

Generated from the delivered files.

| file | item | kind | name | units | layer_type | status | nodata | pixel_size_m | crs | description |
|---|---|---|---|---|---|---|---|---|---|---|
| rasters/jrc_occurrence_review_epsg32642.tif | jrc_occurrence_review | raster band | water_occurrence_pct_1984_2021 | percent of valid observations | reference | external_product | 255.000 | 30.000 | EPSG:32642 | JRC Global Surface Water v1.4 occurrence 1984-2021 (M1 AOI review extent) |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | name |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | verification_status |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | feature_type |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | n_sources |  |  |  |  |  | EPSG:32642 | int64 |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | source_dataset |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | source_url |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | source_version |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | source_licence |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | source_retrieved |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:reference_location | reference_location | vector field | geometry |  |  |  |  |  | EPSG:32642 | geometry |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | aoi_id |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | role |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | mode |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | buffer_m |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | area_km2 |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | config_version |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_primary | aoi_primary | vector field | geometry |  |  |  |  |  | EPSG:32642 | geometry |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | aoi_id |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | role |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | mode |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | buffer_m |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | area_km2 |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | config_version |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:aoi_alternatives | aoi_alternatives | vector field | geometry |  |  |  |  |  | EPSG:32642 | geometry |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | component_id |  |  |  |  |  | EPSG:32642 | int64 |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | area_km2 |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | min_occurrence_pct |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | source |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | note |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:jrc_water_components | jrc_water_components | vector field | geometry |  |  |  |  |  | EPSG:32642 | geometry |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | name |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | featurecla |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | scalerank |  |  |  |  |  | EPSG:32642 | float64 |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | source |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | note |  |  |  |  |  | EPSG:32642 | str |
| indus_delta_handover.gpkg:coarse_indus_centerline | coarse_indus_centerline | vector field | geometry |  |  |  |  |  | EPSG:32642 | geometry |
| tables/image_inventory.csv | image_inventory | table column | dataset |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | series |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | sensor |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | image_id |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | acquired_utc |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | date |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | season |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | label_year |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | scene_cloud_pct |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | valid_fraction |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | compatible |  |  |  |  |  |  | bool |
| tables/image_inventory.csv | image_inventory | table column | usable |  |  |  |  |  |  | bool |
| tables/image_inventory.csv | image_inventory | table column | in_primary_series |  |  |  |  |  |  | bool |
| tables/image_inventory.csv | image_inventory | table column | tile |  |  |  |  |  |  | str |
| tables/image_inventory.csv | image_inventory | table column | orbit_pass |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | relative_orbit |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | polarisations |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | resolution_m |  |  |  |  |  |  | float64 |
| tables/image_inventory.csv | image_inventory | table column | tide_status |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | series |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | season |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | label_year |  |  |  |  |  |  | int64 |
| tables/inventory_summary.csv | inventory_summary | table column | window_start |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | window_end_exclusive |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | completeness |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | data_end |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | n_images |  |  |  |  |  |  | int64 |
| tables/inventory_summary.csv | inventory_summary | table column | n_usable |  |  |  |  |  |  | int64 |
| tables/inventory_summary.csv | inventory_summary | table column | median_valid_fraction |  |  |  |  |  |  | float64 |
| tables/inventory_summary.csv | inventory_summary | table column | first_date |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | last_date |  |  |  |  |  |  | str |
| tables/inventory_summary.csv | inventory_summary | table column | sensors |  |  |  |  |  |  | str |
| tables/missing_observations.csv | missing_observations | table column | series |  |  |  |  |  |  | str |
| tables/missing_observations.csv | missing_observations | table column | season |  |  |  |  |  |  | str |
| tables/missing_observations.csv | missing_observations | table column | label_year |  |  |  |  |  |  | int64 |
| tables/missing_observations.csv | missing_observations | table column | n_images |  |  |  |  |  |  | int64 |
| tables/missing_observations.csv | missing_observations | table column | n_usable |  |  |  |  |  |  | int64 |
| tables/missing_observations.csv | missing_observations | table column | reason |  |  |  |  |  |  | str |
| tables/catalog_verification.csv | catalog_verification | table column | dataset |  |  |  |  |  |  | str |
| tables/catalog_verification.csv | catalog_verification | table column | check |  |  |  |  |  |  | str |
| tables/catalog_verification.csv | catalog_verification | table column | status |  |  |  |  |  |  | str |
| tables/catalog_verification.csv | catalog_verification | table column | detail |  |  |  |  |  |  | str |