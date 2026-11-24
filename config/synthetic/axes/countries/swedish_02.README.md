# swedish_02 -- Swedish country axis

The Swedish country axis. It pairs the simulation config
`config/synthetic/simulation_configs/simulation_config_006_swedish_generative_guided.json`
(guided prompt: refined field descriptions for `employment_type`, `employment_status` and
`parental_structure`, see the README next to that config) with the SCB reference population
(n = 10000, seed 42, ref-v3: region conditional on age group and sex, employment status from
the single register table, students aged 65 and over borrowing the 55-64 income mix) and the
native mapping tier `config/mapping/scb_native`.

## Effect on outputs

The slug format is `{country}_{strategy}_{model}` (`manifest_loader.axis_slug`), so every run of
this axis is named `swedish_02_<strategy>_<model>`, for example
`swedish_02_all_generate_pick_v2_ollama_deepseek_r1_14b`. The mapped reference is
`real_swedish_02`.
