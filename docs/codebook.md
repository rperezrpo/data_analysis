# Codebook

## Rating scale

Rubric `v6_matriz_base.xlsx`, ordinal, five levels:

| Level | Name (EN) | Name (ES) | Rubric column |
|---|---|---|---|
| 1 | Absence | Ausencia | `1_absence` |
| 2 | Awareness | Percepción | `2_awareness` |
| 3 | Competence | Competencia | `3_competence` |
| 4 | Expertise | Experticia | `4_expertise` |
| 5 | Leadership | Liderazgo | `5_leadership` |

## Capacities

| # | `capacidad` | Capacity |
|---|---|---|
| 1 | `nbs_definition` | Understands what a nature-based solution is and its advantages for climate change adaptation and mitigation. |
| 2 | `climate_hazard` | Understands what a climate-related hazard is, how it differs from risk, and how climate change modifies it. |
| 3 | `local_hazard` | Recognises the main climate hazards in one's territory and how socio-spatial conditions increase them. |
| 4 | `identify_landslide` | Knows the key signs for identifying an area at risk of landslides. |
| 5 | `functions_vegetation` | Identifies the functions vegetation has in climate change mitigation and adaptation. |
| 6 | `biobased_materials` | Recognises the potential and limits of biomaterials in construction. |
| 7 | `community_participation` | Recognises the potential and limitations of community organisation in managing environmental initiatives or solutions. |

Wording as in the rubric (`capability_en`); the Spanish wording and the level descriptors are in the rubric too.

## Raw data (`data/raw/`)

**LLM agent JSON** (`A<n>_<model>/E<nn>.json`): `capacidades` is a list of seven objects with

| Field | Content |
|---|---|
| `n` | capacity number (1-7) |
| `slug` | capacity, as `capacidad` above |
| `nivel` | level 1-5 |
| `evidencia` | verbatim quotes from the transcript |
| `justificacion` | the agent's reasoning for the level |

`_modelo` records the model requested and used, whether the call succeeded (`ok`) and its cost in USD.

**Human workbook** (`H<n>_<name>/E<nn>_evaluacion_<name>.xlsx`): the rubric with two columns added, `valor_asignado` (level 1-5; blank = not yet rated) and `evidencia_cita` (supporting quote).

**Keys** (`keys/`): `resultados_v6.1_key.json` maps agent code -> transcript. `clave_evaluacion_externa_v6.xlsx`, sheet `clave`, maps human code (`codigo`) -> transcript (`transcripcion`); its `codigo_anterior` column holds the agents' code.

## `data/processed/ratings_summary.xlsx`

**Sheet `results_vertical`**: one row per interview × capacity (32 × 7 = 224 rows).

| Column | Content |
|---|---|
| `transcripcion` | transcript, `<participante>_<momento>` (e.g. `013_pre`) |
| `participante` | participant code, three digits (text, keeps leading zeros) |
| `momento` | `pre` (before the convite) or `post` (after) |
| `capacidad` | capacity, see above |
| `codigo_A` | blind code under which the LLM agents saw the transcript |
| `codigo_H` | blind code under which the human evaluators saw the transcript |
| `H1` ... `H4` | level given by each human evaluator; blank = not rated |
| `A1`, `A2` | level given by each LLM agent; blank = not rated |

**Sheet `evaluators`**: one row per evaluator column.

| Column | Content |
|---|---|
| `columna` | evaluator column in `results_vertical` |
| `carpeta` | folder read in `data/raw/`; `(not found)` if missing |
| `tipo` | `human` or `LLM agent` |
| `clave` | key used to decode its blind codes |
| `files_read` | interview files read |
| `codes_without_file` | blind codes with no file |
| `ratings_filled` / `ratings_expected` | ratings with a level / 224 |

**Sheet `key`**: one row per transcript with `transcripcion`, `participante`, `momento`, `codigo_A` and `codigo_H`.

**Sheet `warnings`** (only if there were any): problems found while reading.

## `results/tables/reliability_results.xlsx`

**Sheet `reliability`**: one row per group of evaluators × scope.

| Column | Content |
|---|---|
| `group` | `Humans` (H*), `LLM agents` (A*) or `All evaluators` |
| `scope` | `all capacities` (the seven pooled) or one capacity |
| `raters` | evaluators of the group with at least one rating in the scope |
| `n_raters` | number of those evaluators |
| `n_units` | interview × capacity units rated by at least two of them |
| `n_ratings` | ratings in those units |
| `agreement` | mean share of rater pairs giving the identical level per unit |
| `agreement_sd` | SD of that share across units (ddof = 1) |
| `krippendorff_alpha_ordinal` | Krippendorff's alpha, ordinal metric |
| `gwet_ac2_ordinal` | Gwet's AC2, ordinal weights |
| `note` | why a row has no values (fewer than two evaluators with ratings, or no unit rated by two) |

**Sheet `settings`**: the definitions used, as written by the script.
