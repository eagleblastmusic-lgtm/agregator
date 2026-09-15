# Plan rozwoju — Faro Employer Discovery Engine

## 1. Cel produktu

Faro Employer Discovery Engine ma budować możliwie wiarygodną i audytowalną warstwę danych o firmach aktywnie rekrutujących.

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
6. Identyczny NIP/REGON pod różnymi rekordami nie powoduje automatycznego merge przed walidacją reguł.
7. URL firmy z portalu/feedu jest kandydatem, nie automatycznie oficjalną domeną.
8. Oficjalna domena wymaga first-party identity verification.
9. Kontakt jest klasyfikowany kontekstowo; sama obecność e-maila nie oznacza GREEN.
10. Local-part adresu, checkbox marketingowy ani nazwa formularza same w sobie nie są wystarczającym dowodem do poszerzania automatyzacji bez benchmarku.
11. Każda automatyczna reguła rozszerzająca zakres merge/accept musi przejść benchmark jakościowy.
12. Historyczne evidence nie jest nadpisywane; zmiany muszą być audytowalne.

---

## 3. Stan projektu

### M0 — rdzeń enrichmentu

Status: **DONE — funkcjonalny baseline**.

Zaimplementowano:

- modele danych dla firm, ofert, domen, kontaktów i evidence,
- wymienny `SearchProvider`,
- Brave Search provider,
- first-party website crawler,
- respektowanie `robots.txt`,
- limity stron i rate limiting,
- ekstrakcję e-maili i formularzy,
- klasyfikację `GREEN / REVIEW / IGNORE`,
- evidence URL + tekst + signal + confidence,
- CLI,
- testy,
- GitHub Actions CI.

Dalsze zmiany rdzenia traktujemy jako kalibrację jakości, nie budowę fundamentu od zera.

---

### M1 — agregacja ofert pracy

Status: **BASELINE DONE; rozszerzanie źródeł kontrolowane benchmarkiem i dostępnością integracji**.

#### Adaptery

- `olx`,
- `jooble`,
- `adzuna`,
- `careerjet`,
- `epraca`.

#### Infrastruktura

- wspólny kontrakt `JobSource`,
- `SourceRegistry`,
- resumowalne cursor/offset/page tam, gdzie źródło to wspiera,
- `source_state`,
- `source_runs`,
- metryki success/failure,
- liczba stron i ofert,
- insert/update,
- nowe firmy,
- czas runu,
- kontrolowany `benchmark-collect` round-robin,
- importer CSV,
- katalog 91 źródeł,
- eksport danych dla Faro.

`JobPosting` może przenosić:

```text
company_name
company_name_source
company_name_confidence
company_identifiers[]
company_website_candidates[]
```

Careerjet wymaga prawidłowego kontekstu Publisher API. ePraca wymaga wartości `Partner` nadanej integratorowi. Brak konfiguracji nie jest zastępowany sztucznymi danymi ani obchodzeniem autoryzacji.

### Następny gate M1

Benchmark ma określić:

- które źródła realnie dostarczają nowe oferty,
- które dostarczają najlepszą identity data,
- koszt/czas per source,
- error rate,
- overlap ofert,
- wartość identyfikatorów i URL-i firm.

Nie dodajemy kolejnych adapterów tylko po to, aby zwiększać ich liczbę.

---

## 4. M2 — Company Resolution

Status: **V1 DONE; fuzzy auto-merge zablokowany; walidacja produkcyjna wymaga realnego ground truth**.

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
- fuzzy candidates do `resolution-review`,
- brak fuzzy auto-merge,
- pairwise TP/FP/FN/TN,
- precision / recall / F1,
- ground-truth template.

### Jawne identyfikatory przedsiębiorstwa

Status: **DONE — baseline**.

`CompanyIdentifier` przechowuje:

```text
kind
value
source
confidence
```

Persistence przechowuje dodatkowo:

```text
company_id
observation_count
first_seen_at
last_seen_at
```

Normalizowane są m.in. NIP, REGON i KRS. Oficjalny feed ePraca mapuje NIP i REGON z wysokim confidence.

### Konflikty identyfikatorów

```text
identyczny identifier pod >1 company_id
        │
        ▼
REVIEW / benchmark
```

Nie ma automatycznego merge na podstawie samego konfliktu.

### Następny gate M2

Na ręcznie oznaczonej próbce trzeba potwierdzić:

- Company Resolution F1,
- false-positive rate,
- false-negative rate,
- jakość fuzzy REVIEW,
- częstość konfliktów NIP/REGON/KRS,
- czy istnieje bezpieczna reguła wykorzystująca identyfikatory do auto-merge.

Dopiero po tym można rozważyć M2.1.

---

## 5. M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Status: **V1 DONE; source-candidate shortcut + search fallback + structured provenance zaimplementowane**.

### M3.1 — search ranking

Scoring kandydatów wykorzystuje m.in.:

- tokeny nazwy firmy,
- lokalizację,
- host,
- sygnały typu „oficjalna”, „kontakt”,
- wykluczanie oczywistych katalogów/social/job portals.

### M3.2 — first-party identity verification

Search ranking sam nie jest dowodem. Kandydat jest crawlowany, a first-party content służy do potwierdzenia tożsamości firmy.

Verifier bierze pod uwagę m.in.:

- pełną nazwę,
- coverage tokenów nazwy,
- host,
- miasto,
- JSON-LD Organization/Corporation/LocalBusiness,
- search score + content score.

### M3.3 — source-provided website candidates

Status: **DONE — baseline**.

```text
source URL
   │
   ▼
CompanyWebsiteCandidate
   │
   ▼
first-party verification
   │
   ├── ACCEPT -> oficjalna WWW, bez search
   └── REJECT -> SearchProvider fallback
```

Persistence zapisuje:

```text
company_id
url
host
source
confidence
observation_count
first_seen_at
last_seen_at
```

### M3.4 — structured website provenance

Status: **DONE**.

Finalne rozwiązanie domeny:

```text
website_resolution_origin
website_resolution_source
```

Origins:

```text
source_candidate
search
known_url
```

Każda `WebsiteVerificationAttempt` zachowuje:

```text
origin
source
accepted
score
signals
scanned_pages
page_snapshots
```

### Następny gate M3

Ręcznie oznaczony benchmark domen powinien zmierzyć:

- precision,
- recall,
- F1,
- false positive rate,
- source-candidate acceptance rate,
- search fallback rate,
- skuteczność per `website_resolution_source`,
- różnice dla krótkich i długich nazw firm.

---

## 6. M4 — crawler i classifier v2

Status: **IMPLEMENTATION BASELINE DONE; produkcyjna kalibracja pozostaje otwarta**.

### Zaimplementowane

- `sitemap.xml`,
- ograniczona obsługa sitemap index,
- priorytety `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza`,
- typowe obfuskowane adresy e-mail,
- dodatkowe warianty typu `name at domain dot pl`,
- detekcja formularzy,
- semantyka formularza z visible text, `aria-label`, `name`, `id`, `placeholder`, action/method i nazw kontrolek,
- dodatkowe polskie i angielskie sygnały B2B/sales/supplier/franchise,
- role-based local-parts z zachowaniem właściwego `purpose`, ale bez automatycznego GREEN na podstawie samego local-part,
- sygnały zgody na informacje handlowe jako REVIEW, nie automatyczne GREEN,
- konserwatywna kanonikalizacja URL,
- usuwanie fragmentów/default ports/znanych parametrów trackingowych przy zachowaniu parametrów funkcjonalnych,
- deduplikacja aliasów formularzy i linków przed crawl queue,
- append-only `website_verification_runs`,
- `contact_evidence_snapshots`,
- `contact_evidence_observations`,
- SHA-256 evidence,
- `snapshot_changed` dla rzeczywistych zmian treści,
- page snapshots,
- audit każdej próby domeny,
- migracja audit schema dla starszych SQLite,
- osobne metryki classifiera `decision_by_kind` dla `email` i `form`,
- benchmarkowe metryki liczby snapshotów, obserwacji, zmian i kanałów ze zmianami evidence.

### Pozostaje otwarte

- kalibracja classifiera na realnych polskich stronach,
- rozszerzanie obfuskacji tylko na podstawie faktycznie obserwowanych wariantów,
- walidacja semantyki formularzy na realnym ground truth,
- decyzja, czy produkcyjne gate’y powinny mieć osobne minima dla `email` i `form`,
- walidacja stabilności timeline evidence przy cyklicznych recrawlach,
- ewentualna polityka pełniejszych snapshotów/content digests i retencji.

### Gate zamykający M4

M4 można uznać za produkcyjnie gotowe dopiero po ręcznym benchmarku kontaktów.

Aktualny globalny gate:

```text
Contact decision macro F1 >= 0.90
```

`decision_by_kind` jest obecnie diagnostyczne. Ewentualne osobne progi dla typów kanału należy ustalić dopiero po zebraniu wystarczającego supportu w realnym ground truth.

---

## 7. Quality benchmark — najbliższy główny checkpoint

Status: **TO DO na realnych danych; infrastruktura benchmarkowa gotowa**.

Najbliższy pełny gate to kontrolowana próbka **1000 realnych ofert**.

### Preflight

```bash
agregator-benchmark preflight \
  --sources olx,jooble,adzuna \
  --strict
```

### Kontrolowany run

```bash
agregator-benchmark run \
  --db benchmark/benchmark.sqlite3 \
  --output-dir benchmark/run \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100 \
  --enrichment-batch-size 25 \
  --max-enrichment-companies 1000 \
  --strict
```

Workflow:

```text
collection
  -> Company Resolution
  -> enrichment
  -> website verification
  -> contact crawl/classification
  -> benchmark report
  -> dataset export
  -> immutable evidence export
  -> ground-truth templates
```

### Ręczny labeling

```bash
agregator-benchmark status \
  --label-dir benchmark/run/labels \
  --strict
```

### Ewaluacja

```bash
agregator-benchmark evaluate \
  --db benchmark/benchmark.sqlite3 \
  --label-dir benchmark/run/labels \
  --fail-on-error
```

### Aktualne domyślne progi

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

Progi są początkowymi założeniami technicznymi. Produkcyjne wartości należy zatwierdzić po realnym labelingu.

---

## 8. Metryki benchmarku

`benchmark` jest technicznym dashboardem jakości i pokrycia.

### Agregacja

```text
jobs_total
companies_total
sources_total
source_job_counts
source_run_metrics
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

## 9. Employer Discovery Score

Status: **baseline zaimplementowany; wagi wymagają kalibracji po benchmarku**.

Score służy do priorytetyzacji firm, nie do określania prawdziwości danych.

Przykładowe sygnały:

```text
+ aktywne oferty
+ wiele źródeł ofert
+ wysoka identity confidence
+ zweryfikowana oficjalna domena
+ strona współpracy/B2B
+ GREEN channel
```

Należy utrzymać ścisłe rozdzielenie:

```text
Employer Discovery Score != Company Resolution confidence
Employer Discovery Score != Website confidence
Employer Discovery Score != Contact confidence
```

---

## 10. Eksport Faro

Status: **schema v7**.

Aktualny bundle:

```text
companies.csv
job_postings.csv
company_identifiers.csv
company_website_candidates.csv
contact_channels.csv
website_verification_runs.csv
contact_evidence_snapshots.csv
contact_evidence_observations.csv
website_page_snapshots.csv
manifest.json
```

`website_verification_runs.csv` zachowuje finalne provenance i wszystkie próby domen.

`website_page_snapshots.csv` zawiera offline evidence dla zaakceptowanych i odrzuconych prób domen.

`contact_evidence_snapshots.csv` zawiera immutable wersje evidence kontaktów.

`contact_evidence_observations.csv` tworzy append-only timeline:

```text
website_verification_run_id
contact_channel_id
snapshot_id
content_sha256
decision
purpose
confidence
evidence_url
evidence_signal
snapshot_changed
captured_at
```

Eksport jest interoperacyjną granicą między silnikiem discovery a przyszłą warstwą Faro/API.

---

## 11. M5 — persistence v2 i API

Status: **PLANNED; nie zaczynać przed benchmarkiem jakości M0–M4**.

Preferowany kierunek:

```text
PostgreSQL
    │
    ├── immutable audit/event history
    ├── current materialized state
    ├── review queues
    └── Faro API
```

### Docelowe encje

```text
companies
company_aliases
company_locations
company_identifiers
company_website_candidates
job_postings
contact_channels
website_verification_runs
contact_evidence_snapshots
contact_evidence_observations
source_runs
review_decisions
```

### API — pierwsza wersja

Planowane read endpoints/use cases:

```text
companies actively recruiting
company detail
jobs by company
companies with GREEN channel
companies requiring REVIEW
website verification history
contact evidence history
source health
benchmark metrics
```

Write endpoints powinny najpierw obejmować ręczne decyzje REVIEW i labeling, a nie outreach.

---

## 12. M6 — review workspace i human-in-the-loop

Status: **PLANNED**.

Zakres:

- review potencjalnych duplikatów firm,
- review konfliktów identyfikatorów,
- review domen,
- review kontaktów,
- podgląd immutable evidence i historii zmian,
- zapisywanie decyzji operatora,
- reason codes,
- wersjonowanie decyzji,
- ponowna ewaluacja reguł po zmianach.

To powinno być źródłem przyszłych danych kalibracyjnych/treningowych.

---

## 13. M7 — rozszerzanie źródeł po benchmarku

Status: **PLANNED**.

Po benchmarku 1000 ofert źródła należy dodawać według wartości, a nie liczby.

Priorytet źródła powinien uwzględniać:

```text
unikalne oferty
identity quality
jawne identyfikatory firmy
jawny URL firmy
stabilność integracji
koszt requestów
error rate
warunki użycia
pokrycie rynku polskiego
```

Źródło o wysokim overlap i niskiej jakości identity może być mniej wartościowe niż mniejsze źródło z NIP/REGON/WWW.

---

## 14. M8 — observability i operacje produkcyjne

Status: **PLANNED**.

Zakres docelowy:

- health dashboard per source,
- alerty spadku liczby ofert,
- alerty wzrostu błędów,
- latency i koszt per source,
- latency i koszt per enrichment,
- procent search fallback,
- acceptance rate source website candidates,
- drift klasyfikacji kontaktów,
- drift Company Resolution,
- tempo zmian evidence,
- audit retention policy,
- backup/restore.

---

## 15. M9 — integracja z aplikacją Faro

Status: **PLANNED po stabilizacji API**.

Silnik agregatora powinien dostarczać Faro dane, ale nie przejmować odpowiedzialności interfejsu użytkownika.

Przykładowe dane dla Faro:

```text
company
job postings
source provenance
identity confidence
verified website
website resolution origin/source
contact channels
contact evidence
contact evidence history
Employer Discovery Score
review flags
```

Oddzielenie silnika od aplikacji pozwala niezależnie rozwijać discovery, UI i model biznesowy.

---

## 16. Co robimy teraz

Najbliższa kolejność rozwoju:

```text
P0  utrzymać CI GREEN
 │
 ▼
P1  zamrozić baseline M0–M4
 │
 ▼
P2  wykonać preflight konfiguracji realnego benchmarku
 │
 ▼
P3  zebrać kontrolowaną próbkę 1000 ofert
 │
 ▼
P4  wykonać enrichment + benchmark techniczny
 │
 ▼
P5  wyeksportować dataset v7 + immutable evidence + ground truth
 │
 ▼
P6  ręcznie oznaczyć Company / Website / Contact truth
 │
 ▼
P7  uruchomić quality-gate
 │
 ├── PASS ─► kalibracja wag + decyzja o M5/M7
 │
 └── FAIL ─► poprawki reguł oparte na błędach + ponowny benchmark
```

Najważniejsza zasada na tym etapie: **nie zwiększać automatyzacji identity/contact acceptance przed pomiarem jakości na realnych danych**.
