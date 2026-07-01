"""Generate N realistic Italian demographic profiles using conditional sampling from ISTAT/Eurostat data."""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from population_synthetic.clients.eurostat_client import EurostatClient
from population_synthetic.clients.istat_client import ISTATSDMXClient
from population_synthetic.generators.reference.italy.fetch_service import ISTATFetchService
from population_synthetic.generators.reference.italy.sample_service import ISTATSampleService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic Italian population from ISTAT/Eurostat data"
    )
    parser.add_argument(
        "--n", type=int, default=100, help="Number of individuals to generate"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="istat_population.json",
        help="Output file path (default: data/istat_api/istat_population.json)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    if args.seed is None:
        args.seed = int(np.random.SeedSequence().entropy & 0xFFFFFFFF)
    logger.info("Seed: %d", args.seed)

    eurostat_client = EurostatClient()
    istat_client = ISTATSDMXClient()
    distributions = ISTATFetchService.load_all(eurostat_client, istat_client)

    rng = np.random.default_rng(args.seed)
    individuals = ISTATSampleService.sample_population(distributions, rng, args.n)

    _TABLE_NOTES: dict[str, str] = {
        "demo_pjan": "Population by single year of age and sex (Eurostat demo_pjan)",
        "demo_r_pjangrp3": "Population by NUTS2 region (Eurostat demo_r_pjangrp3)",
        "demo_r_d2jan": "Population by NUTS2 region fallback (Eurostat demo_r_d2jan)",
        "ilc_lvho02": "Housing tenure by income group (Eurostat EU-SILC ilc_lvho02)",
        "ilc_lvph02": "Household composition / parental structure (Eurostat ilc_lvph02)",
        "ilc_lvph03": "Household size distribution (Eurostat ilc_lvph03)",
        "migr_pop1ctz": "Population by citizenship / birth location (Eurostat migr_pop1ctz)",
        "migr_pop1ctz#detail": "Birth country detail — top origin countries (Eurostat migr_pop1ctz)",
        "52_1194_DF_DCCV_POPTIT1_UNT2020_1": "Population by education level, age, sex (ISTAT 52_1194)",
        "150_938": "Employment by sex, education, occupation (ISTAT 150_938 / LFS)",
        "150_938#industry": "Industry sector from ISTAT 150_938 OCCUPATION_2011 dimension",
        "150_938#employment_type": "Employment type (FT/PT x perm/temp) from ISTAT 150_938",
        "32_292": "Household income and structure by type (ISTAT 32_292 / EU-SILC)",
        "22_289_DF_DCIS_POPRES1_25": "Civil status by age and sex (ISTAT 22_289)",
    }

    tables_used = [
        {"table": tag, "notes": _TABLE_NOTES.get(tag, tag)}
        for tag in distributions.tables_used
    ]

    output = {
        "metadata": {
            "country": "Italy",
            "source": "ISTAT SDMX REST + Eurostat JSON-stat API",
            "output_format": "raw",
            "tables_used": tables_used,
            "data_vintage": "2021-2023",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": args.n,
            "seed": args.seed,
        },
        "individuals": individuals,
    }

    output_path = Path(args.output)
    if output_path.suffix != ".json":
        output_path = output_path.with_suffix(".json")
    if output_path.parent == Path("."):
        output_path = Path("data/istat_api") / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d individuals to %s", args.n, output_path)
    logger.info("Tables used: %s", list(distributions.tables_used))


if __name__ == "__main__":
    main()
