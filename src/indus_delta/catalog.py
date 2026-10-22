"""Verify dataset registry entries against the official Earth Engine catalog (STAC).

The catalog is published by Google as static STAC JSON and needs no authentication. A pass
here means the identifier, type, temporal extent, bands, scale/offset and QA definitions in
our configuration match the catalog. It does not show that an account can read the data or
that images exist over the AOI; the authenticated inventory does that.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from indus_delta.config import Configs, DatasetEntry

log = logging.getLogger(__name__)

# An open-ended request against a collection whose last image is older than this is flagged.
ENDED_AFTER_DAYS = 90

_KIND_TO_GEE_TYPE = {"image": "image", "image_collection": "image_collection", "table": "table"}


@dataclass(frozen=True)
class CatalogCheck:
    dataset: str
    check: str
    status: str  # PASS / WARN / FAIL
    detail: str


def stac_url(root: str, entry: DatasetEntry) -> str:
    if entry.stac_path:
        return f"{root.rstrip('/')}/{entry.stac_path}"
    first = entry.ee_id.split("/", 1)[0]
    return f"{root.rstrip('/')}/{first}/{entry.ee_id.replace('/', '_')}.json"


def fetch_json(url: str, retries: int = 3) -> tuple[dict | None, str | None]:
    """(record, error). 404 is returned as an error without retrying."""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
                return json.loads(resp.read()), None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, "not found in catalog (HTTP 404)"
            err = f"HTTP {exc.code}"
        except (OSError, json.JSONDecodeError) as exc:
            err = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return None, err


def _bands(record: dict) -> dict[str, dict]:
    return {b["name"]: b for b in record.get("summaries", {}).get("eo:bands", [])}


def _bitmask_parts(band: dict) -> dict[int, str]:
    bm = band.get("gee:bitmask") or {}
    parts = bm.get("bitmask_parts", []) if isinstance(bm, dict) else bm
    return {int(p["first_bit"]): str(p["description"]) for p in parts}


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def catalog_extent(record: dict) -> tuple[date, date] | None:
    try:
        start, end = record["extent"]["temporal"]["interval"][0]
        return _parse_date(start), _parse_date(end)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_entry(
    key: str, entry: DatasetEntry, record: dict, cfgs: Configs, today: date
) -> list[CatalogCheck]:
    out: list[CatalogCheck] = []

    def add(check: str, ok: bool | None, detail: str, warn: bool = False) -> None:
        status = "PASS" if ok else ("WARN" if warn else "FAIL")
        out.append(CatalogCheck(key, check, status, detail))

    add(
        "id_matches",
        record.get("id") == entry.ee_id,
        f"catalog id {record.get('id')!r}, configured {entry.ee_id!r}",
    )
    gee_type = record.get("gee:type")
    add(
        "type_matches",
        gee_type == _KIND_TO_GEE_TYPE.get(entry.kind),
        f"catalog type {gee_type!r}, configured kind {entry.kind!r}",
    )
    status = record.get("gee:status")
    add(
        "status_ready",
        status in (None, "ready"),
        f"gee:status {status!r}",
        warn=status == "deprecated",
    )

    ext = catalog_extent(record)
    if ext is None:
        add("temporal_extent", False, "catalog record has no temporal extent")
    else:
        req_start = entry.use_period.start
        open_end = entry.use_period.end is None
        req_end = entry.use_period.end or today
        overlap = ext[0] <= req_end and ext[1] >= req_start
        # An open-ended request means "latest available": only the start must be covered.
        full = ext[0] <= req_start and (open_end or ext[1] >= req_end)
        shown_end = "latest" if open_end else req_end
        detail = f"catalog {ext[0]}..{ext[1]}; requested {req_start}..{shown_end}" + (
            ""
            if full or not overlap
            else f"; usable {max(ext[0], req_start)}..{min(ext[1], req_end)}"
        )
        ended = open_end and ext[1] < today - timedelta(days=ENDED_AFTER_DAYS)
        if ended:
            detail += f"; collection ended {ext[1]} (no data after this date)"
        add(
            "temporal_extent",
            overlap and full and not ended,
            detail,
            warn=overlap and (not full or ended),
        )

    bands = _bands(record)
    missing = [b for b in entry.required_bands if b not in bands]
    add(
        "required_bands",
        not missing,
        "all required bands present" if not missing else f"missing bands {missing}",
    )

    if entry.reflectance_scale is not None:
        sr = [b for b in entry.required_bands if b in bands and re.fullmatch(r"(SR_)?B\d+", b)]
        bad = []
        for b in sr:
            scale = bands[b].get("gee:scale", 1.0)
            offset = bands[b].get("gee:offset", 0.0)
            if not (
                abs(scale - entry.reflectance_scale) < 1e-12
                and abs(offset - (entry.reflectance_offset or 0.0)) < 1e-12
            ):
                bad.append(f"{b}: catalog {scale}/{offset}")
        add(
            "scale_offset",
            not bad,
            f"{len(sr)} bands match scale {entry.reflectance_scale}, offset "
            f"{entry.reflectance_offset or 0.0}"
            if not bad
            else "; ".join(bad),
        )

    out += _qa_checks(key, entry, bands, cfgs)
    return out


def _qa_checks(key: str, entry: DatasetEntry, bands: dict, cfgs: Configs) -> list[CatalogCheck]:
    pp = cfgs.preprocessing
    out = []
    if key in pp.landsat.members:
        sensor = pp.landsat.members[key]
        parts = _bitmask_parts(bands.get("QA_PIXEL", {}))
        bad = [
            f"bit {b.bit}: config {b.description!r}, catalog {parts.get(b.bit)!r}"
            for b in pp.landsat.qa_pixel_mask_bits
            if (b.sensors is None or sensor in b.sensors)
            and _norm(parts.get(b.bit, "")) != _norm(b.description)
        ]
        out.append(
            CatalogCheck(
                key,
                "qa_pixel_bits",
                "FAIL" if bad else "PASS",
                "; ".join(bad) or "configured QA_PIXEL bits match the catalog",
            )
        )
        if pp.landsat.mask_saturated_bands:
            rad = _bitmask_parts(bands.get("QA_RADSAT", {}))
            used = cfgs.indices.sensors[sensor].bands.values()
            bad = []
            for b in used:
                n = int(b.removeprefix("SR_B"))
                if _norm(rad.get(n - 1, "")) != _norm(f"Band {n} data saturated"):
                    bad.append(f"{b}: bit {n - 1} is {rad.get(n - 1)!r}")
            out.append(
                CatalogCheck(
                    key,
                    "qa_radsat_bits",
                    "FAIL" if bad else "PASS",
                    "; ".join(bad) or "saturation bit n-1 <-> SR_Bn confirmed",
                )
            )
    if key == pp.sentinel2.dataset:
        classes = {
            int(c["value"]): str(c["description"])
            for c in bands.get(pp.sentinel2.scl_band, {}).get("gee:classes", [])
        }
        bad = [
            f"{c.value}: config {c.description!r}, catalog {classes.get(c.value)!r}"
            for c in pp.sentinel2.scl_mask_classes
            if _norm(classes.get(c.value, "")) != _norm(c.description)
        ]
        out.append(
            CatalogCheck(
                key,
                "scl_classes",
                "FAIL" if bad else "PASS",
                "; ".join(bad) or "configured SCL mask classes match the catalog",
            )
        )
    if key == pp.sentinel2.cloud_score_plus.dataset:
        band = pp.sentinel2.cloud_score_plus.band
        out.append(
            CatalogCheck(
                key,
                "cloud_score_band",
                "PASS" if band in bands else "FAIL",
                f"band {band!r} {'present' if band in bands else 'missing'}",
            )
        )
    return out


def run_catalog_check(cfgs: Configs, today: date | None = None) -> tuple[list[CatalogCheck], dict]:
    today = today or datetime.now(UTC).date()
    root = cfgs.preprocessing.catalog.stac_root
    checks: list[CatalogCheck] = []
    records: dict[str, dict] = {}
    for key, entry in cfgs.datasets.datasets.items():
        if not entry.ee_id:
            checks.append(
                CatalogCheck(
                    key,
                    "catalog_entry",
                    "WARN" if entry.optional else "FAIL",
                    "no Earth Engine ID configured; the dataset must be supplied as an uploaded "
                    "asset or local raster with a recorded DOI",
                )
            )
            continue
        url = stac_url(root, entry)
        log.info("fetching %s", url)
        record, err = fetch_json(url)
        if record is None:
            checks.append(
                CatalogCheck(
                    key, "catalog_entry", "WARN" if entry.optional else "FAIL", f"{url}: {err}"
                )
            )
            continue
        raw = json.dumps(record, sort_keys=True).encode()
        ext = catalog_extent(record)
        records[key] = {
            "ee_id": entry.ee_id,
            "stac_url": url,
            "record_sha256": hashlib.sha256(raw).hexdigest(),
            "title": record.get("title"),
            "gee_type": record.get("gee:type"),
            "version": record.get("version"),
            "status": record.get("gee:status"),
            "temporal_extent": [ext[0].isoformat(), ext[1].isoformat()] if ext else None,
            "license": record.get("license"),
            "terms_links": [
                link["href"] for link in record.get("links", []) if link.get("rel") == "license"
            ],
        }
        checks.append(CatalogCheck(key, "catalog_entry", "PASS", url))
        result = verify_entry(key, entry, record, cfgs, today)
        if entry.optional:
            result = [
                CatalogCheck(
                    c.dataset, c.check, "WARN" if c.status == "FAIL" else c.status, c.detail
                )
                for c in result
            ]
        checks += result
    return checks, records


def checks_to_rows(checks: list[CatalogCheck]) -> list[dict]:
    return [asdict(c) for c in checks]


def record_in_registry(
    path: Path, checks: list[CatalogCheck], records: dict, verified_by: str, today: date
) -> list[str]:
    """Mark datasets whose catalog checks have no FAIL as catalog_verified in datasets.yaml.

    Line-based edit so that comments survive; only the `verification:` line of each dataset
    and the lines this function itself writes are touched. Returns the updated keys.
    """
    failed = {c.dataset for c in checks if c.status == "FAIL"}
    lines = path.read_text(encoding="utf-8").splitlines()
    out, key, updated = [], None, []
    managed = ("verified_on:", "verified_by:", "catalog_extent:")
    for line in lines:
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            key = stripped[:-1]
        if (
            line.startswith("    ")
            and stripped.startswith(managed)
            and key in records
            and key not in failed
        ):
            continue  # rewritten below
        if line.startswith("    verification:") and key in records and key not in failed:
            current = stripped.split(":", 1)[1].strip()
            level = "verified" if current == "verified" else "catalog_verified"
            ext = records[key]["temporal_extent"]
            out += [
                f"    verification: {level}",
                f'    verified_on: "{today.isoformat()}"',
                f'    verified_by: "{verified_by}"',
                f'    catalog_extent: {{start: "{ext[0]}", end: "{ext[1]}"}}',
            ]
            updated.append(key)
            continue
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return updated
