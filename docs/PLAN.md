# Plan rozwoju — Faro Employer Discovery Engine

## 1. Cel produktu

Faro Employer Discovery Engine ma zbudować możliwie wiarygodną, audytowalną warstwę danych o firmach aktywnie rekrutujących.

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
3. Każdy istotny wynik musi zachować provenance i confidence.
4. Fuzzy similarity nie jest samodzielnym dowodem tożsamości firmy.
5. Fuzzy Company Resolution pozostaje REVIEW-only do czasu walidacji na ground truth.
6. Identyczny NIP/REGON pod różnymi rekordami nie powoduje automatycznego merge przed walidacją reguł.
7. URL firmy podany przez portal/feed jest kandydatem, nie automatycznie oficjalną domeną.
8. Oficjalna domena wymaga first-party identity verification.
9. Kontakt jest klasyfikowany kontekstowo; sama obecność e-maila nie oznacza GREEN.
10. Każda automatyczna reguła rozszerzająca zakres merge/accept musi przejść benchmark jakościowy.

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
- limit stron i rate limiting,
- ekstrakcję e-maili i formularzy,
- klasyfikację `GREEN / REVIEW / IGNORE`,
- evidence URL + tekst + signal + confidence,
- CLI,
- testy,
- GitHub Actions CI.

Kryteria M0 są spełnione. Dalsze zmiany rdzenia powinny być traktowane jako kalibracja jakości, nie budowa fundamentu od zera.

---

### M1 — agregacja ofert pracy

Status: **BASELINE DONE; rozszerzanie źródeł kontrolowane benchmarkiem i dostępnością integracji**.

#### Zaimplementowane adaptery

- `olx`,
- `jooble`,
- `adzuna`,
- `careerjet`,
- `epraca`.

#### Zaimplementowana infrastruktura

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

#### Interfejs logiczny adaptera

```text
collect(cursor) -> SourceBatch(
    jobs=JobPosting[],
    next_cursor=...
)
```

`JobPosting` może obecnie przenosić nie tylko podstawową ofertę, ale także:

```text
company_name
company_name_source
company_name_confidence
company_identifiers[]
company_website_candidates[]
```

#### Integracje wymagające konfiguracji partnera

Careerjet wymaga prawidłowego kontekstu Publisher API. ePraca wymaga wartości `Partner` nadanej integratorowi przez właściwy system. Brak konfiguracji nie jest zastępowany sztucznymi danymi ani obchodzeniem autoryzacji.

#### Następny gate M1

Nie dodajemy kolejnych adapterów tylko po to, aby zwiększać liczbę integracji. Najpierw benchmark ma określić:

- które źródła realnie dostarczają nowe oferty,
- które źródła dostarczają najlepszą identity data,
- koszt/czas per source,
- error rate,
- overlap ofert między źródłami,
- wartość dodatkowych identyfikatorów i URL-i firm.

---

## 4. M2 — Company Resolution

Status: **V1 DONE; fuzzy auto-merge zablokowany; walidacja produkcyjna wymaga realnego ground truth**.

### Zaimplementowany baseline

- normalizacja nazw,
- usuwanie/normalizacja form prawnych,
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
- pairwise evaluator TP/FP/FN/TN,
- precision / recall / F1,
- ground-truth template.

### Jawne identyfikatory przedsiębiorstwa

Status: **DONE — warstwa bazowa**.

`CompanyIdentifier` przechowuje:

```text
kind
value
source
confidence
```

Warstwa persistence przechowuje dodatkowo:

```text
company_id
observation_count
first_seen_at
last_seen_at
```

Normalizowane są m.in.:

- NIP,
- REGON,
- KRS.

Oficjalny feed ePraca mapuje NIP i REGON z wysokim confidence.

### Konflikty identyfikatorów

Jeśli jeden identyfikator występuje pod więcej niż jednym `company_id`:

```text
identifier conflict -> REVIEW / benchmark
```

Nie ma automatycznego merge na podstawie samego konfliktu.

### Następny gate M2

Na ręcznie oznaczonej próbce trzeba potwierdzić:

- Company Resolution F1,
- false-positive rate,
- false-negative rate,
- jakość fuzzy REVIEW,
- częstość konfliktów NIP/REGON/KRS,
- czy istnieje wystarczająco bezpieczna reguła wykorzystująca identyfikatory do auto-merge.

Dopiero po tym można rozważyć M2.1 z mocniejszymi automatycznymi regułami.

---

## 5. M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Status: **V1 DONE; source-candidate shortcut + search fallback + structured provenance zaimplementowane**.

### M3.1 — search ranking

Zaimplementowano scoring kandydatów na podstawie m.in.:

- tokenów nazwy firmy,
- lokalizacji,
- hosta,
- sygnałów typu „oficjalna”, „kontakt”,
- wykluczania oczywistych katalogów/social/job portals.

### M3.2 — first-party identity verification

Po rankingu sama pozycja w wyszukiwarce nie wystarcza. Kandydat jest crawlowany, a treść first-party jest używana do potwierdzenia tożsamości firmy.

Verifier bierze pod uwagę m.in.:

- pełną nazwę,
- coverage tokenów nazwy,
- host,
- miasto,
- JSON-LD Organization/Corporation/LocalBusiness,
- wynik search score + content score.

### M3.3 — source-provided website candidates

Status: **DONE — baseline**.

Źródła mogą dostarczyć `CompanyWebsiteCandidate`:

```text
url
source
confidence
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

Przykład:

```text
ePraca adresWww
    │
    ▼
CompanyWebsiteCandidate
    │
    ▼
first-party verification
    │
    ├── ACCEPT -> oficjalna WWW, bez search
    │
    └── REJECT -> Brave/SearchProvider fallback
```

### M3.4 — structured website provenance

Status: **DONE**.

Finalne rozwiązanie domeny zapisuje:

```text
website_resolution_origin
website_resolution_source
```

Dozwolone origins:

```text
source_candidate
search
known_url
```

Przykładowe sources:

```text
official_feed.adresWww
brave
static
scan_known_website
```

Każda `WebsiteVerificationAttempt` zachowuje także własne:

```text
origin
source
accepted
score
signals
scanned_pages
page_snapshots
```

Dzięki temu nie trzeba rekonstruować provenance przez parsowanie luźnych stringów sygnałów.

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

Status: **PARTIAL — mocne fundamenty gotowe, kalibracja i rozszerzenia pozostają otwarte**.

### Zaimplementowane

- `sitemap.xml`,
- ograniczona obsługa sitemap index,
- priorytety stron:
  - `/kontakt`,
  - `/wspolpraca`,
  - `/partnerzy`,
  - `/b2b`,
  - `/dla-firm`,
  - `/dostawcy`,
  - `/franczyza`,
- typowe obfuskowane adresy e-mail,
- detekcja formularzy,
- sygnały zgody na informacje handlowe jako REVIEW, nie automatyczne GREEN,
- append-only `website_verification_runs`,
- `contact_evidence_snapshots`,
- SHA-256 evidence,
- page snapshots,
- audit każdej próby domeny,
- migracja audit schema dla starszych baz SQLite.

### Do zrobienia w M4

- bogatsza semantyka formularzy,
- więcej wariantów obfuskacji adresów,
- pełniejsze snapshoty/hash całych stron lub kontrolowany content digest,
- deduplikacja formularzy i aliasów URL,
- kalibracja classifiera na realnych polskich stronach,
- osobne statystyki classifiera wg typu kanału,
- dokładniejszy model zmian evidence w czasie.

### Gate zamykający M4

M4 można uznać za produkcyjnie gotowe dopiero po ręcznym benchmarku kontaktów i osiągnięciu ustalonego progu macro F1 dla `GREEN / REVIEW / IGNORE`.

Aktualny domyślny gate:

```text
Contact decision macro F1 >= 0.90
```

---

## 7. Quality benchmark — najbliższy główny checkpoint

Status: **TO DO na realnych danych**.

Najbliższy pełny gate to kontrolowana próbka **1000 realnych ofert**.

### Kolejność

```text
1. benchmark-collect
2. benchmark
3. enrichment
4. export-quality-labels
5. ręczny labeling
6. evaluate-resolution
7. evaluate-website
8. evaluate-contacts
9. quality-gate
10. decyzja: kalibrować czy rozszerzać automatyzację
```

### Komendy bazowe

```bash
agregator benchmark-collect \
  --db agregator.sqlite3 \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100

agregator benchmark --db agregator.sqlite3

agregator enrich-db \
  --db agregator.sqlite3 \
  --limit 1000

agregator export-quality-labels \
  --db agregator.sqlite3 \
  --output-dir benchmark/labels \
  --job-limit 1000 \
  --company-limit 1000 \
  --contact-limit 1000
```

Po ręcznym oznaczeniu:

```bash
agregator quality-gate \
  --db agregator.sqlite3 \
  --resolution-truth benchmark/labels/company_resolution_truth.csv \
  --website-truth benchmark/labels/website_resolution_truth.csv \
  --contact-truth benchmark/labels/contact_classification_truth.csv \
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

Aktualny `benchmark` powinien być traktowany jako techniczny dashboard jakości i pokrycia.

Obejmuje m.in.:

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
```

### Kontakty

```text
contact_channels_total
green_channels
review_channels
ignored_channels
green_company_rate
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

Status: **schema v5**.

Aktualny bundle:

```text
companies.csv
job_postings.csv
company_identifiers.csv
company_website_candidates.csv
contact_channels.csv
website_verification_runs.csv
contact_evidence_snapshots.csv
manifest.json
```

`website_verification_runs.csv` zawiera m.in.:

```text
outcome
website_url
website_confidence
resolution_origin
resolution_source
verification_signals_json
search_candidates_json
website_attempts_json
scanned_pages_json
```

Eksport jest obecnie interoperacyjną granicą między silnikiem discovery a przyszłą warstwą Faro/API.

---

## 11. M5 — persistence v2 i API

Status: **PLANNED; nie zaczynać przed benchmarkiem jakości M0–M4**.

### Cel

Przenieść warstwę danych z lokalnego SQLite/bundle do produkcyjnego storage i stabilnego API.

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
source health
benchmark metrics
```

Write endpoints powinny najpierw obejmować ręczne decyzje REVIEW i labeling, a nie outreach.

---

## 12. M6 — review workspace i human-in-the-loop

Status: **PLANNED**.

Cel: zamienić istniejące kolejki REVIEW i CSV ground truth w wygodny workflow operatorski.

Zakres:

- review potencjalnych duplikatów firm,
- review konfliktów identyfikatorów,
- review domen,
- review kontaktów,
- zapisywanie decyzji operatora,
- reason codes,
- wersjonowanie decyzji,
- możliwość ponownej ewaluacji modelu/reguł po zmianach.

To powinno być źródłem przyszłych danych treningowych/regułowych do kalibracji.

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
P1  zamrozić obecny baseline M0–M4
 │
 ▼
P2  zebrać kontrolowaną próbkę 1000 ofert
 │
 ▼
P3  wykonać enrichment i benchmark techniczny
 │
 ▼
P4  wyeksportować pakiet ground truth
 │
 ▼
P5  ręcznie oznaczyć Company / Website / Contact truth
 │
 ▼
P6  uruchomić quality-gate
 │
 ├── PASS ─► kalibracja wag + decyzja o M5/M7
 │
 └── FAIL ─► poprawki reguł + ponowny benchmark
```

Najważniejsza zasada na tym etapie: **nie zwiększać automatyzacji identity resolution przed pomiarem jej jakości na realnych danych**.
