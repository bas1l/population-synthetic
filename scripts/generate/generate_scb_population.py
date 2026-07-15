"""Generate N realistic Swedish demographic profiles using conditional sampling from SCB data."""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from population_synthetic.clients.scb_client import SCBPxWebClient
from population_synthetic.generators.real.sweden.fetch_service import FetchService
from population_synthetic.generators.real.sweden.sample_service import SampleService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic Swedish population from SCB data")
    parser.add_argument("--n", type=int, default=100, help="Number of individuals to generate")
    parser.add_argument("--output", type=str, default="data/scb_api/scb_population.json", help="Output file path")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--merge-status-education",
        action="store_true",
        help=(
            "Opt-in: condition employment_status on (age x education x sex) by merging "
            "two REGISTER tables via the documented odds-multiplication derivation "
            "(assumes no status x age x education interaction). Default OFF = the "
            "single-table (age x sex) register path."
        ),
    )
    args = parser.parse_args()

    if args.seed is None:
        args.seed = int(np.random.SeedSequence().entropy & 0xFFFFFFFF)
    logger.info("Seed: %d", args.seed)

    client = SCBPxWebClient()
    distributions = FetchService.load_all(client, merge_status_education=args.merge_status_education)
    if args.merge_status_education:
        logger.info(
            "employment_status two-table MERGE enabled (all-register; assumes no "
            "status x age x education interaction) -- see the merge spec"
        )

    rng = np.random.default_rng(args.seed)
    individuals = SampleService.sample_population(
        distributions, rng, args.n, merge_status_education=args.merge_status_education
    )

    _TABLE_CLASSIFICATION_MAP: dict[str, dict[str, str]] = {
        "BE/BE0101/BE0101A/BefolkningNy": {
            "notes": "Population by age, sex, region, civil status (BE0101)",
        },
        "BE/BE0101/BE0101A/BefolkningNy#region": {
            "notes": "County-level population distribution (BE0101, LAU/NUTS region codes)",
        },
        "BE/BE0101/BE0101A/BefolkningNy#civil_status": {
            "notes": "Civil status distribution by age/sex (BE0101, civilstand codes OG/G/ANKL/SK)",
        },
        "UF/UF0506/UF0506B/Utbildning": {
            "classification": "SUN2020",
            "notes": "Education level by age/sex (Standard for svensk utbildningsnomenklatur 2020)",
        },
        "AM/AM0401/AM0401P/NAKUBefUtbNivAr": {
            "classification": "AKU + SUN2020",
            "notes": "Employment status by education level (AKU Labour Force Survey + SUN2020 education codes)",
        },
        "BE/BE0101/BE0101E/FolkmFodlandHVD": {
            "notes": "Foreign-born population by birth country group (BE0101E)",
        },
        "BE/BE0101/BE0101E/FodelselandArK": {
            "classification": "ISO 3166-1 alpha-2",
            "notes": "Detailed birth country by age/sex (ISO country codes)",
        },
        "HE/HE0110/HE0110A/SamForvInk1": {
            "notes": "Number of persons by income bracket, age, and sex (HE0110A, individual gross income in SEK thousands)",
        },
        "HE/HE0110/HE0110F/TabVX13InkStruktN": {
            "notes": "Income source by employment status and age (HE0110 income component codes)",
        },
        "LE/LE0102/LE0102B/LE0102T17": {
            "notes": "Parental/family structure (LE0102 living conditions)",
        },
        "AM/AM0401/AM0401I/AKURLSysSNI07Ar": {
            "classification": "SNI2007 (NACE Rev. 2)",
            "notes": "Employed persons by industry sector (AKU, Standard for svensk naringsgrensindelning 2007 / NACE Rev. 2)",
        },
        "AM/AM0401/AM0401I/AKURLSysAnkAr": {
            "classification": "AKU",
            "notes": "Employment attachment type by age/sex (AKU Labour Force Survey -- permanent/temporary/self-employed)",
        },
        "AM/AM0401/AM0401S/NAKUSysselOkArbtidAr": {
            "classification": "AKU",
            "notes": "Usual weekly working hours by age/sex (AKU Labour Force Survey)",
        },
        "BO/BO0104/BO0104D/BO0104T04": {
            "notes": "Housing tenure by dwelling type (BO0104 housing stock statistics, tenure codes 1-3)",
        },
        "BE/BE0101/BE0101S/HushallT03": {
            "notes": "Household size distribution (BE0101S household statistics)",
        },
    }

    tables_used = [
        {"table": tag, **_TABLE_CLASSIFICATION_MAP.get(tag, {})}
        for tag in distributions.tables_used
    ]

    output = {
        "metadata": {
            "source": "SCB PxWeb API",
            "output_format": "raw",
            "tables_used": tables_used,
            "data_vintage": "2024",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": args.n,
            "seed": args.seed,
        },
        "individuals": individuals,
    }

    output_path = Path(args.output)
    if output_path.parent == Path("."):
        output_path = Path("data/scb_api") / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d individuals to %s", args.n, output_path)
    logger.info("Tables used: %s", list(distributions.tables_used))


if __name__ == "__main__":
    main()
