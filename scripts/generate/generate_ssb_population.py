"""Generate N realistic Norwegian demographic profiles using conditional sampling from SSB data."""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from population_synthetic.clients.ssb_client import SSBPxWebClient
from population_synthetic.generators.real.norway.fetch_service import SSBFetchService
from population_synthetic.generators.real.norway.sample_service import SSBSampleService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic Norwegian population from SSB data"
    )
    parser.add_argument(
        "--n", type=int, default=100, help="Number of individuals to generate"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ssb_population.json",
        help="Output file path (default: data/ssb_api/ssb_population.json)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    if args.seed is None:
        args.seed = int(np.random.SeedSequence().entropy & 0xFFFFFFFF)
    logger.info("Seed: %d", args.seed)

    client = SSBPxWebClient()
    distributions = SSBFetchService.load_all(client)

    rng = np.random.default_rng(args.seed)
    individuals = SSBSampleService.sample_population(distributions, rng, args.n)

    _TABLE_NOTES: dict[str, str] = {
        "07459": "Population by age, sex, region (SSB table 07459 -- Folkemengde)",
        "07459#region": "Fylke-level population distribution (SSB 07459, post-2024 fylke codes)",
        "08921": "Education level by age band and sex (SSB table 08921 -- UtdanNivaa)",
        "13785": "Employment status by education level and sex (SSB table 13785 -- ArbStyrkStatus)",
        "03031#civil_status": "Civil status by decade age band and sex (SSB table 03031 -- EkteskStatus)",
        "09315": "Employed persons by NACE2007 industry sector (SSB table 09315)",
        "13878": "Employment contract type x working hours x age x sex (SSB table 13878)",
        "11081": "Dwelling tenure form by EierStatus (SSB table 11081)",
        "06079": "Household size distribution (SSB table 06079 -- HushStr)",
        "09817": "Immigrant population by world-region background (SSB table 09817 -- Landbakgrunn)",
        "09817#detail": "Birth country detail by age/sex -- top 20 origin countries (SSB 09817)",
        "06083": "Family type distribution (SSB table 06083 -- FamilieType)",
        "06655": "Individual gross income by bracket x age x sex (SSB table 06655 -- BruttoInn)",
        "ssb_income_source#approximate": (
            "Income source by employment status and age -- approximate distributions "
            "(no SSB PxWebApi v2 table provides income-component shares "
            "conditioned jointly on employment status and age group)"
        ),
    }

    tables_used = [
        {"table": tag, "notes": _TABLE_NOTES.get(tag, tag)}
        for tag in distributions.tables_used
    ]

    output = {
        "metadata": {
            "country": "Norway",
            "source": "SSB PxWebApi v2",
            "output_format": "raw",
            "tables_used": tables_used,
            "data_vintage": "2023-2024",
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
        output_path = Path("data/ssb_api") / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d individuals to %s", args.n, output_path)
    logger.info("Tables used: %s", list(distributions.tables_used))


if __name__ == "__main__":
    main()
