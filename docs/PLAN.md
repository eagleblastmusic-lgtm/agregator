# Plan rozwoju — Faro Employer Discovery Engine

## 1. Cel produktu

Faro Employer Discovery Engine buduje możliwie wiarygodną i audytowalną warstwę danych o firmach aktywnie rekrutujących.

Docelowy przepływ:

```text
publiczna oferta pracy
        │
        ▼
normalizacja oferty
        │
        ▼
Company Resolution
        │
        ├──────────────► jawne identyfikatory firmy
        │                 NIP / REGON / KRS / source IDs
        │
        ▼
źródłowy kandydat WWW
        │
        ├── verified ──► oficjalna WWW
        │
        └── rejected
                │
                ▼
         SearchProvider
                │
                ▼
      first-party verification
                │
                ▼
         oficjalna WWW
                │
                ▼
        first-party crawler
                │
                ▼
Contact / Intent Extractor
                │
                ▼
GREEN / REVIEW / IGNORE
                │
                ▼
Evidence + Audit + Export/API
```

Repo **nie wysyła wiadomości**. Outreach pozostaje poza zakresem silnika discovery.

---

## 2. Zasady projektowe

1. Tylko publicznie dostępne dane i autoryzowane źródła partnerskie/API.
2. Brak obchodzenia logowania, CAPTCHA, paywalli i kontroli dostępu.
3. Każdy istotny wynik zachowuje provenance i confidence.
4. Fuzzy similarity nie jest samodzielnym dowodem tożsamości firmy.
5. Fuzzy Company Resolution pozostaje REVIEW-only do czasu walidacji na ground truth.
6. Identyczny NIP/REGON/KRS pod różnymi rekordami nie powoduje automatycznego merge przed walidacją reguł.
7. URL firmy z portalu/feedu jest kandydatem, nie automatycznie oficjalną domeną.
8. Oficjalna domena wymaga first-party identity verification.
9. Kontakt jest klasyfikowany kontekstowo; sama obecność e-maila nie oznacza GREEN.
10. Automatyczne poszerzanie merge/acceptance musi przejść benchmark jakościowy.
11. Historyczne evidence nie jest nadpisywane; zmiany muszą być audytowalne.
12. Źródła eksperymentalne wymagają jawnego opt-in w kontrolowanych runach.
13. Najpierw mierzymy źródła i jakość, potem rozszerzamy automatyzację.

---

## 3. Stan projektu w skrócie

```text
M0  rdzeń enrichmentu                    DONE baseline
M1  agregacja źródeł                     DONE baseline / real-source validation pending
M2  Company Resolution                   V1 DONE / ground truth pending
M3  official website resolution          V1 DONE / ground truth pending
M4  crawler + contact classifier v2      baseline DONE / calibration pending

QB  real quality benchmark               infrastructure DONE / real run pending
M5  PostgreSQL + Faro API                PLANNED after quality gate
M6  review workspace / human-in-loop     PLANNED
M7  rozszerzanie źródeł                  PLANNED after benchmark
M8  observability / production ops       PLANNED
M9  integracja z aplikacją Faro          PLANNED after API stabilization
```

Najbliższym ryzykiem nie jest już brak fundamentów kodu, lecz **niezwalidowana jakość na realnych danych**.

---

## 4. M0 — rdzeń enrichmentu

Status: **DONE — funkcjonalny baseline**.

Zaimplementowano:

- modele firm, ofert, domen, kontaktów i evidence,
- wymienny `SearchProvider`,
- Brave Search provider,
- first-party website crawler,
- `robots.txt`, limity stron i rate limiting,
- ekstrakcję e-maili i formularzy,
- klasyfikację `GREEN / REVIEW / IGNORE`,
- evidence URL + tekst + signal + confidence,
- CLI,
- testy,
- GitHub Actions CI.

Dalsze zmiany M0 są kalibracją, a nie budową fundamentu od zera.

---

## 5. M1 — agregacja ofert i diagnostyka źródeł

Status: **BASELINE DONE; real-source validation pending**.

### Zarejestrowane adaptery

```text
olx
jooble
adzuna
careerjet
epraca
```

### Source access policy

`SourceRegistry` zapisuje:

```text
name
access_mode
experimental
notes
```

Aktualnie:

```text
jooble     partner_api
adzuna     partner_api
careerjet  partner_api
epraca     official_partner_feed
olx        public_web_endpoint + experimental
```

OLX nie wchodzi automatycznie do kontrolowanego benchmarku. Wymaga jawnego `--allow-experimental-sources`.

### Infrastruktura

- wspólny kontrakt `JobSource`,
- resumowalne cursor/offset/page tam, gdzie źródło to wspiera,
- `source_state`,
- `source_runs`,
- success/failure i runtime metrics,
- round-robin collector,
- importer CSV,
- katalog 91 źródeł,
- source overlap / exclusivity,
- identity quality per source,
- employer-evidence provenance per source,
- source diagnostics bez jednego arbitralnego Source Value Score.

`JobPosting` może przenosić:

```text
company_name
company_name_source
company_name_confidence
company_identifiers[]
company_website_candidates[]
```

`company_identifier_observations` i `company_website_candidate_observations` zachowują `job_source + evidence_source`, więc kilka integracji może dostać własny provenance/credit za ten sam NIP/REGON/WWW.

### M1.1 — collection-only smoke gate

Status: **IMPLEMENTED; real run pending**.

Entry point:

```bash
agregator-collect sources
agregator-collect preflight --sources jooble,adzuna --strict
agregator-collect run \
  --sources jooble,adzuna \
  --target-jobs 100 \
  --max-rounds 10 \
  --strict
```

Smoke nie wymaga Brave Search ani crawlowania stron firm.

Collector kończy pełną rundę round-robin przed sprawdzeniem targetu. Dzięki temu pierwsze wysokowolumenowe źródło nie odcina późniejszych źródeł w tej samej rundzie.

Strict readiness wymaga:

```text
collection_target_reached = true
source_health_ready = true
```

Source health blokuje run, jeśli żądane źródło:

- nie wykonało udanego runu,
- zostało disabled,
- albo nie zwróciło żadnej oferty.

Manifest collection-only ma schema v2 i przechowuje m.in. `unexercised_sources`, `disabled_sources`, `sources_without_jobs`, `sources_with_errors` i `blockers`.

Manualny workflow `.github/workflows/collection-smoke.yml` generuje artifact i czytelny GitHub Step Summary.

### Gate M1

Na realnym smoke/benchmarku trzeba zmierzyć:

- realny wolumen per source,
- paginację/cursor,
- error rate,
- latency,
- identity quality,
- city/description coverage,
- NIP/REGON/WWW coverage,
- exclusivity/overlap,
- stabilność integracji.

Nie dokładamy kolejnych adapterów tylko po to, aby zwiększać ich liczbę.

---

## 6. M2 — Company Resolution

Status: **V1 DONE; produkcyjna walidacja wymaga realnego ground truth**.

### Baseline

- normalizacja nazw i form prawnych,
- `company_aliases`,
- `company_locations`,
- exact name + city,
- konserwatywny exact cross-city,
- blokada ryzykownego cross-city merge dla nazw krótkich/ogólnych,
- stabilny fallback dla brakującej lokalizacji,
- `company_resolution_method`,
- `company_resolution_confidence`,
- fuzzy candidates do REVIEW,
- brak fuzzy auto-merge,
- pairwise TP/FP/FN/TN,
- precision / recall / F1,
- ground-truth tooling.

### Jawne identyfikatory

`CompanyIdentifier` zachowuje kind/value/source/confidence. Persistence dodatkowo liczy observation count i first/last seen. Normalizowane są m.in. NIP, REGON i KRS. ePraca mapuje NIP i REGON z wysokim confidence.

Konflikt identycznego identyfikatora pod wieloma `company_id` trafia do REVIEW; nie powoduje auto-merge.

### Gate M2

Na ręcznie oznaczonej próbce trzeba potwierdzić:

- Company Resolution F1,
- false-positive rate,
- false-negative rate,
- jakość fuzzy REVIEW,
- częstość konfliktów identifierów,
- czy można bezpiecznie rozszerzyć reguły auto-merge.

Docelowy początkowy gate:

```text
Company Resolution F1 >= 0.95
```

---

## 7. M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Status: **V1 DONE; produkcyjna walidacja wymaga realnego ground truth**.

### Search ranking

Scoring wykorzystuje m.in. tokeny nazwy, lokalizację, host i sygnały official/contact oraz wyklucza oczywiste social/job/directory domains.

### First-party identity verification

Search ranking sam nie jest dowodem. Kandydat jest crawlowany, a first-party content służy do potwierdzenia tożsamości firmy.

Verifier bierze pod uwagę m.in.:

- pełną nazwę,
- token coverage,
- host,
- miasto,
- JSON-LD `Organization` / `Corporation` / `LocalBusiness`,
- search score + content score.

### Source-provided website candidates

```text
source URL
   │
   ▼
CompanyWebsiteCandidate
   │
   ▼
first-party verification
   │
   ├── ACCEPT -> oficjalna WWW bez search
   └── REJECT -> SearchProvider fallback
```

### Structured website provenance

Finalne rozwiązanie zapisuje:

```text
website_resolution_origin = source_candidate | search | known_url
website_resolution_source
```

Każda `WebsiteVerificationAttempt` zachowuje origin/source/accepted/score/signals/scanned pages/page snapshots.

### Gate M3

Ręcznie oznaczony benchmark domen ma zmierzyć:

- precision,
- recall,
- F1,
- wrong-domain / false-positive rate,
- source candidate acceptance rate,
- search fallback rate,
- skuteczność per resolution source,
- zachowanie dla krótkich i długich nazw firm.

Początkowy gate:

```text
Website Resolution F1 >= 0.95
```

---

## 8. M4 — crawler i classifier v2

Status: **IMPLEMENTATION BASELINE DONE; produkcyjna kalibracja pending**.

Zaimplementowano m.in.:

- `sitemap.xml` i ograniczone sitemap index,
- priorytety `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza`,
- typowe publiczne obfuskacje e-maili,
- detekcję i semantykę formularzy,
- polskie i angielskie sygnały B2B/sales/supplier/franchise,
- role-based local-parts bez automatycznego GREEN,
- sygnały zgody handlowej jako REVIEW, nie automatyczne GREEN,
- konserwatywną kanonikalizację URL,
- deduplikację aliasów formularzy/linków,
- append-only `website_verification_runs`,
- `contact_evidence_snapshots`,
- `contact_evidence_observations`,
- SHA-256 evidence,
- `snapshot_changed`,
- page snapshots,
- osobne metryki `decision_by_kind` dla `email` i `form`.

### Gate M4

Realny benchmark kontaktów musi zwalidować:

- globalną jakość GREEN/REVIEW/IGNORE,
- jakość `email` vs `form`,
- semantykę formularzy,
- publiczne warianty obfuskacji,
- stabilność evidence timeline przy recrawlach.

Początkowy gate:

```text
Contact decision macro F1 >= 0.90
```

---

## 9. Quality Benchmark — główny checkpoint

Status: **INFRASTRUCTURE DONE; real run + manual labels pending**.

Docelowy przebieg:

```text
A. collection smoke 50–100 ofert
       │
       ▼
B. source health + identity/provenance review
       │
       ▼
C. controlled collection do >=1000 ofert
       │
       ▼
D. enrichment
       │
       ├── website verification
       └── contact crawl/classification
       │
       ▼
E. benchmark report + dataset v8 + immutable evidence
       │
       ▼
F. deterministic stratified sample
       │
       ▼
G. blind primary labeling
       │
       ▼
H. quality gate
       │
       ├── PASS -> calibration + M5/M7 decision
       └── FAIL -> error-driven rule fixes -> repeat benchmark
```

Full benchmark:

```bash
agregator-benchmark preflight --sources jooble,adzuna --strict

agregator-benchmark run \
  --db benchmark/benchmark.sqlite3 \
  --output-dir benchmark/run \
  --sources jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100 \
  --enrichment-batch-size 25 \
  --max-enrichment-companies 1000 \
  --strict
```

Pełny benchmark wymaga SearchProvider/Brave. Jest resumowalny; live source health jest celowo osobnym smoke gate, aby wznowienie enrichmentu na już zebranej bazie nie wymagało ponownego pobierania ofert.

### Blind labeling

Główne truth CSV nie zawierają predykcji systemu. Prediction-rich kopie trafiają do `prediction_reference/`. `label-reference` ujawnia reference dopiero po zapisaniu niezależnej etykiety truth dla danego wiersza.

Sampling jest deterministyczny i warstwowy; Company Resolution rezerwuje część budżetu na pairwise anchors.

---

## 10. Metryki benchmarku

### Agregacja i źródła

```text
jobs_total
companies_total
sources_total
source_job_counts
source_run_metrics
source_overlap
source_identity_metrics
source_provenance_metrics
```

### Company Resolution

```text
company_resolution_counts
company_identifiers_total
companies_with_identifiers
identifier_company_rate
identifier_conflicts
```

### WWW

```text
websites_found
website_find_rate
website_candidates_total
companies_with_website_candidates
source_verified_websites
source_website_candidate_company_rate
source_verified_website_rate
source_verified_share_of_found
website_resolution_origin_counts
source_verified_website_counts
source_website_attempt_metrics
```

### Kontakty i evidence

```text
contact_channels_total
green_channels
review_channels
ignored_channels
green_company_rate
contact_evidence_snapshots_total
contact_evidence_observations_total
contact_evidence_changes_total
changed_contact_channels
```

### Biznesowa priorytetyzacja

```text
employer_score_average
employer_score_ge_60
employer_score_distribution
```

---

## 11. Employer Discovery Score

Status: **baseline zaimplementowany; wagi wymagają kalibracji po benchmarku**.

Score służy do priorytetyzacji firm, nie do określania prawdziwości danych.

Należy utrzymać rozdzielenie:

```text
Employer Discovery Score != Company Resolution confidence
Employer Discovery Score != Website confidence
Employer Discovery Score != Contact confidence
```

---

## 12. Eksport Faro

Status: **schema v8**.

Aktualny bundle:

```text
companies.csv
job_postings.csv
company_identifiers.csv
company_identifier_observations.csv
company_website_candidates.csv
company_website_candidate_observations.csv
contact_channels.csv
website_verification_runs.csv
contact_evidence_snapshots.csv
contact_evidence_observations.csv
website_page_snapshots.csv
manifest.json
```

Eksport jest interoperacyjną granicą między silnikiem discovery a przyszłą warstwą Faro/API.

---

## 13. M5 — persistence v2 i API

Status: **PLANNED; nie zaczynać przed quality benchmarkiem M0–M4**.

Preferowany kierunek:

```text
PostgreSQL
    │
    ├── immutable audit/event history
    ├── current materialized state
    ├── review queues
    └── Faro API
```

Pierwsza wersja API powinna obsługiwać przede wszystkim read use cases oraz ręczne decyzje REVIEW/labeling, nie outreach.

---

## 14. M6 — review workspace / human-in-the-loop

Status: **PLANNED**.

Zakres:

- review potencjalnych duplikatów firm,
- review konfliktów identyfikatorów,
- review domen,
- review kontaktów,
- immutable evidence + historia zmian,
- operator decisions + reason codes,
- wersjonowanie decyzji,
- ponowna ewaluacja po zmianie reguł.

---

## 15. M7 — rozszerzanie źródeł

Status: **PLANNED after benchmark**.

Źródła należy dodawać według wartości, a nie liczby. Priorytet ma uwzględniać unikalne oferty, identity quality, NIP/REGON/WWW, stabilność, koszt requestów, error rate, warunki użycia i pokrycie rynku PL.

---

## 16. M8 — observability i operacje produkcyjne

Status: **PLANNED**.

Docelowo:

- source health dashboard,
- alerts dla spadku ofert/błędów,
- latency/koszt per source i enrichment,
- search fallback i source-candidate acceptance,
- drift classifiera i Company Resolution,
- evidence change rate,
- audit retention,
- backup/restore.

---

## 17. M9 — integracja z aplikacją Faro

Status: **PLANNED after API stabilization**.

Silnik ma dostarczać Faro dane, ale pozostaje oddzielony od UI. Przykładowy kontrakt: company, jobs, source provenance, identity confidence, verified website, resolution provenance, contact channels/evidence/history, Employer Discovery Score i review flags.

---

## 18. Co robimy teraz

Aktualna kolejność P0–P9:

```text
P0  utrzymać CI GREEN
 │
 ▼
P1  zamrozić baseline M0–M4
 │
 ▼
P2  skonfigurować realne API/partner credentials
 │
 ▼
P3  collection smoke 50–100 ofert
 │
 ├── FAIL -> naprawa konkretnego adaptera/config
 │
 └── PASS
       │
       ▼
P4  zebrać >=1000 realnych ofert
 │
 ▼
P5  enrichment + benchmark techniczny
 │
 ▼
P6  dataset v8 + immutable evidence + blind labels
 │
 ▼
P7  ręczny Company / Website / Contact truth
 │
 ▼
P8  quality gate
 │
 ├── PASS -> kalibracja wag + decyzja M5/M7
 │
 └── FAIL -> poprawki oparte na error analysis + ponowny benchmark
 │
 ▼
P9  dopiero potem M5/M6/M7/M8/M9
```

Najważniejsza zasada na tym etapie: **nie zwiększać automatyzacji identity/contact acceptance przed pomiarem jakości na realnych danych**.
