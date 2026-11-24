# simulation_config_006_swedish_generative_guided

The Swedish simulation config used by the `swedish_02` country axis. Three field `description`
strings are written to name what a valid answer must contain, so that an answer maps onto the
target schema without the prompt enumerating any canonical value.

| field | description |
|---|---|
| `parental_structure` | "The family composition the persona grew up in as a child, specifically which parents were present." |
| `employment_status` | "Whether the persona is currently in work, and if not, their main current activity instead." |
| `employment_type` | "The type of employment contract the persona holds, not the occupation or job title, including its duration and the number of weekly working hours." |

## Design intent: value-agnostic

The descriptions clarify the **question**, not the **answer**. They name the *dimensions* of a
valid answer (duration and working hours for `employment_type`) and the *subject* (which parents
were present), but do not enumerate the canonical category values. The free-generation paradigm
stays intact: the model invents its own value. The `instruction` block carries no global
"answer with a canonical label" line.

Runs on this config are written under the country id `swedish_02`
(`config/synthetic/axes/countries/swedish_02.yaml`).
