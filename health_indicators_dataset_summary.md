# NFHS-5 District Health Indicators Dataset Summary

Source file: `output/data/raw_nfhs_5_district_health_indicators.csv`  
Databricks table referenced by the build script: `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators`

## 1. High-level description

This third dataset is a district-level health and household indicator table for India, apparently sourced from NFHS-5-style district factsheets. It has 706 district rows across 36 states/union territories and 109 columns, with each row representing a district plus survey sample sizes and percentage-based indicators.

The table is best used as geographic context for planning or prioritization. It is not a facility-level performance table: when joined to facilities, the same district indicators are repeated for every facility in that district.

Key shape notes:

| Item | Observed value |
|---|---:|
| Rows | 706 |
| Columns | 109 |
| States/UTs | 36 |
| Duplicate `state_ut` + `district_name` keys | 0 |
| Columns with missing values | 0 |
| Median households surveyed per district | 908 |
| Median women 15-49 interviewed per district | 1,020 |
| Median men 15-54 interviewed per district | 145 |

The row-level unit matters: these are district summaries, not individual records. The male respondent sample is much smaller than the female sample, so male-specific district estimates can be noisier.

## 2. Tricky fields, traps, and mapping to other tables

### Primary key and cleanup

Use the normalized pair `state_ut` + `district_name` as the natural key. Do not join on `district_name` alone because district names repeat across states.

Field traps observed in the raw file:

- `district_name` has trailing spaces in 704 of 706 rows. Always trim before joining.
- `state_ut` also has whitespace issues, for example ` Lakshadweep `.
- The file uses `Maharastra` instead of `Maharashtra`. This is a major join trap because India Post and facility data use `MAHARASHTRA`.
- Some district names use older or alternate spellings compared with current postal data: examples include `Gurgaon` vs `Gurugram`, `Bangalore` vs `Bengaluru Urban`, `Belgaum` vs `Belagavi`, `Mysore` vs `Mysuru`, `Darjiling` vs `Darjeeling`, `Haora` vs `Howrah`, `Hugli` vs `Hooghly`, `Kancheepuram` vs `Kanchipuram`, and `Thoothukkudi` vs `Tuticorin`.
- Some current postal districts did not exist as separate NFHS-5 districts, especially newer Andhra Pradesh and Tamil Nadu districts. These need a district crosswalk, not just fuzzy matching.

### Numeric field traps

Most indicator columns ending in `_pct` are percentages. A few numeric fields are not percentages:

- `households_surveyed`, `women_15_49_interviewed`, and `men_15_54_interviewed` are survey counts.
- `sex_ratio_total_f_per_1000_m` and `sex_ratio_at_birth_5y_f_per_1000_m` are ratios per 1,000 males.
- `average_out_of_pocket_expenditure_per_delivery_in_a_public_fac` is a currency/expenditure measure, not a percent.

Several column names encode NFHS footnote numbers, such as `_7`, `_10`, `_16_17`, `_18`, `_19`, `_20`, and `_22`. Those are definition cues from the source survey documentation and should not be treated as semantic parts of the metric unless mapped back to the original codebook.

### Mapping to facility and pincode tables

The health table has no pincode, facility ID, latitude, or longitude. The practical mapping path is:

1. `raw_facilities_selected.csv` or `facility_health_cleaned.csv`: start with facility `unique_id`, address fields, and `address_zipOrPostcode`.
2. Extract a six-digit Indian PIN into `pincode_extracted`.
3. Join `pincode_extracted` to `pincode_bridge.csv`.
4. Use `pincode_primary_state` and `pincode_primary_district` from the pincode bridge.
5. Normalize state and district strings.
6. Join to the NFHS table on normalized `state_ut` + `district_name`.

The cleaned output already includes join metadata:

- `join_strategy`
- `join_confidence`
- `join_match_score`
- `join_uncertainty_reason`
- `pincode_is_ambiguous`
- `health_need_score`
- `medical_desert_priority_score`

In the current cleaned facility output, health joins work for many rows but still require review:

| Join strategy | Facility rows |
|---|---:|
| `pincode_district_state_exact` | 6,645 |
| `pincode_district_state_fuzzy` | 152 |
| `facility_city_state_fallback` | 219 |
| `pincode_only_no_health_match` | 2,772 |
| `no_valid_pincode` | 195 |
| `unjoined` | 105 |

The biggest observed miss is Maharashtra: 1,573 facility rows with `pincode_primary_state = MAHARASHTRA` did not receive health indicators because the NFHS file spells the state `Maharastra`. Add an alias for this before trusting join coverage.

Also treat `pincode_is_ambiguous = true` as a real uncertainty flag. Some pincodes map to multiple districts or states in India Post, so a modal pincode-to-district bridge can be convenient but not definitive.

## 3. Health indicators covered

The table is broad. It covers these major groups:

- Survey sample sizes: households surveyed, women interviewed, men interviewed.
- Demographics and registration: age structure, sex ratio, sex ratio at birth, birth registration, death registration.
- Household infrastructure: electricity, improved water, improved sanitation, clean cooking fuel, iodized salt.
- Insurance and education: health insurance coverage, female schooling, female literacy.
- Marriage, fertility, and menstrual hygiene: early marriage, adolescent motherhood/pregnancy, menstrual hygiene, higher-order births.
- Family planning: any method, modern method, sterilization, IUD, pill, condom, injectables, unmet need, counseling.
- Maternal care: first-trimester ANC, 4+ ANC visits, tetanus protection, iron-folic acid consumption, MCP card, postnatal care.
- Delivery care: institutional births, public facility births, skilled birth attendance, home births handled by skilled personnel, C-sections, public/private C-section rates.
- Child immunization: full vaccination, BCG, polio, pentavalent/DPT, measles-containing vaccine, rotavirus, hepatitis/pentavalent, vitamin A, public/private vaccination source.
- Child illness and care seeking: diarrhea prevalence, ORS, zinc, care seeking for diarrhea, ARI/fever symptoms, ARI/fever care seeking.
- Infant and young child feeding: early breastfeeding, exclusive breastfeeding, solid/semi-solid foods, adequate diet.
- Nutrition and anthropometrics: child stunting, wasting, severe wasting, underweight, overweight, women's underweight/overweight/obesity, high waist-hip ratio.
- Anaemia: child anaemia, non-pregnant women, pregnant women, all women 15-49, adolescent girls.
- Non-communicable disease markers: high/very high blood sugar and high blood pressure for women and men.
- Preventive screening: cervical cancer screening, breast examination, oral cancer examination among women 30-49.
- Risk behaviors: tobacco use and alcohol consumption for women and men.

## 4. Interesting data trends

These observations are unweighted district-level summaries, not population-weighted national estimates.

### Maternal and delivery care is generally high, but uneven

Institutional births average 88.7% across districts, with a median of 92.2%. Skilled birth attendance averages 89.6%. The floor is still very low in some districts: Mon, Nagaland has 21.4% institutional births and 30.9% skilled birth attendance.

C-section rates are highly uneven. The district mean is 22.8%, the 90th percentile is 46.8%, and Karimnagar, Telangana reaches 82.4%. This could indicate very different care access, practice patterns, facility mix, or denominator effects by district.

### Child nutrition indicators show persistent need

Adequate diet among children 6-23 months is low: mean 11.9%, median 10.6%, and 10th percentile 4.0%. Child stunting averages 33.5%, wasting averages 18.5%, and underweight averages 29.5%.

Extreme district values are large:

- Stunting maximum: 60.6% in Pashchimi Singhbhum, Jharkhand.
- Underweight maximum: 62.4% in Pashchimi Singhbhum, Jharkhand.
- Wasting maximum: 48.0% in Karimganj, Assam.

### Anaemia is widespread

Anaemia among women 15-49 averages 55.9% across districts, with a median of 57.2% and 90th percentile of 70.4%. The highest observed value is 93.5% in Leh(Ladakh), Ladakh.

District-level women's anaemia and child anaemia move together: Pearson correlation is about 0.65 in this file. That makes anaemia a strong cross-cutting need signal for maternal and child health planning.

### NCD markers are non-trivial and geographically correlated

High blood pressure and high blood sugar are meaningful adult health burdens in the district summaries:

| Indicator | District mean | District median |
|---|---:|---:|
| Women 15+ high BP | 21.4% | 21.0% |
| Men 15+ high BP | 24.8% | 24.4% |
| Women 15+ high/very high blood sugar | 12.5% | 11.7% |
| Men 15+ high/very high blood sugar | 14.7% | 14.1% |

Male and female district patterns are strongly aligned: high BP correlation is about 0.86, and high/very high blood sugar correlation is about 0.91. This suggests district-level risk environments rather than isolated gender-specific signals.

### Preventive cancer screening is extremely low

Cancer screening indicators are among the starkest findings:

| Screening indicator | Mean | Median | 90th percentile |
|---|---:|---:|---:|
| Cervical screening, women 30-49 | 1.6% | 0.6% | 4.2% |
| Breast exam, women 30-49 | 0.7% | 0.2% | 1.3% |
| Oral cancer exam, women 30-49 | 0.7% | 0.3% | 1.6% |

This is useful for prevention and outreach planning, but it should not be interpreted as facility screening capacity. It measures whether women report ever undergoing screening/exams.

### Education and household conditions are linked to other health indicators

Female schooling and early marriage are strongly inversely related. The Pearson correlation between women with 10+ years of schooling and women age 20-24 married before age 18 is about -0.65.

Clean cooking fuel and institutional births also show a moderate positive association, with Spearman correlation around 0.59. This is not causal evidence by itself, but it is a useful socioeconomic gradient for prioritization.

### Tobacco and alcohol show large gender gaps

Tobacco use averages 40.6% among men versus 11.6% among women. Alcohol consumption averages 23.2% among men versus 2.9% among women. The highest male tobacco state average is Mizoram at about 73.8%, while high alcohol values are concentrated in parts of the Northeast.

## 5. Practical analysis guidance

For hackathon use, this table is valuable for district-level need scoring, outreach targeting, and contextualizing facility supply. Good derived signals include:

- Maternal access: low institutional births, low skilled birth attendance, low ANC coverage.
- Child health burden: high stunting, wasting, underweight, anaemia, low adequate diet.
- Adult chronic disease burden: high BP and high blood sugar for men and women.
- Preventive care gaps: low cervical, breast, and oral cancer screening.
- Socioeconomic context: female literacy, schooling, sanitation, clean cooking fuel, insurance coverage.

Recommended implementation guardrails:

- Keep a normalized district/state key table or crosswalk instead of relying only on fuzzy matching.
- Add state aliases for `Maharastra` -> `Maharashtra` before joining.
- Preserve join confidence and uncertainty fields in any user-facing app.
- Label every facility-level health value as district context, not as a facility attribute.
- Avoid ranking districts from single indicators alone; combine indicators by theme and show the components.
- If producing official estimates, use NFHS documentation and survey weights. The summaries above are unweighted across district rows.
