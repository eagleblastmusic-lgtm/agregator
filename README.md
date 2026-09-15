# Agregator — Faro Employer Discovery Engine

Silnik Faro do budowania bazy firm aktywnie rekrutujących, rozwiązywania ich tożsamości, weryfikowania oficjalnych stron WWW oraz wykrywania publicznych kanałów współpracy B2B z pełnym provenance i audit trail.

```text
oferta pracy
  -> firma
  -> Company Resolution
  -> kandydat WWW
  -> first-party verification
  -> crawl
  -> kanał współpracy
  -> evidence + confidence
```

Projekt **nie wysyła wiadomości**, nie omija logowania, CAPTCHA, paywalli ani kontroli dostępu i nie próbuje pozyskiwać niepublicznych danych kontaktowych. Integracje partnerskie/API działają wyłącznie z prawidłową konfiguracją i autoryzacją.

## Aktualny zakres M0–M4

- wspólny `JobSource` + `SourceRegistry`,
- adaptery: `olx`, `jooble`, `adzuna`, `careerjet`, `epraca`,
- katalog 91 źródeł w `config/source_catalog.tsv`,
- resumowalne pobieranie + `source_runs`,
- kontrolowany collector round-robin,
- Company Resolution v1 z konserwatywnym exact-match i fuzzy REVIEW-only,
- aliasy/lokalizacje firm,
- jawne identyfikatory przedsiębiorstw z provenance/confidence,
- NIP/REGON z oficjalnego feedu ePraca,
- konflikty identyfikatorów bez automatycznego merge,
- źródłowe kandydatury WWW, np. ePraca `adresWww`,
- first-party verification domeny przed uznaniem jej za oficjalną,
- search fallback przez wymienny `SearchProvider` (Brave),
- strukturalne provenance rozwiązania domeny: `source_candidate`, `search`, `known_url`,
- crawler first-party z `robots.txt`, limitami, rate limitingiem i `sitemap.xml`,
- ekstrakcja e-maili, formularzy i wariantów publicznej obfuskacji,
- bogatsza semantyka formularzy z atrybutów i kontrolek,
- konserwatywna kanonikalizacja i deduplikacja aliasów URL,
- klasyfikacja `GREEN / REVIEW / IGNORE`,
- osobne metryki klasyfikatora dla `email` i `form`,
- append-only audit website verification i evidence,
- immutable SHA-256 page/contact snapshots,
- append-only timeline `contact_evidence_observations`,
- ręcznie etykietowane quality gates dla Company Resolution, domen i kontaktów,
- Employer Discovery Score 0–100,
- kontrolowany benchmark end-to-end 1000 ofert,
- eksport Faro **schema v7**.

## Instalacja

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

Po instalacji dostępne są dwa entrypointy:

```text
agregator
agregator-benchmark
```

## Konfiguracja

Najważniejsze zmienne są w `.env.example`.

```text
BRAVE_SEARCH_API_KEY=
JOOBLE_API_KEY=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
CAREERJET_API_KEY=
CAREERJET_REFERER=
CAREERJET_USER_IP=
CAREERJET_USER_AGENT=
EPRACA_PARTNER=
```

Careerjet wymaga rzeczywistego kontekstu partnera. ePraca wymaga wartości `Partner` nadanej integratorowi i prawidłowego zakresu zapytania. Repo nie podstawia fikcyjnych danych i nie obchodzi autoryzacji.

## Podstawowe użycie

```bash
agregator db-init --db agregator.sqlite3
agregator sources
agregator collect --source olx --pages 2
agregator companies --db agregator.sqlite3 --limit 50
agregator enrich-db --db agregator.sqlite3 --limit 20
agregator benchmark --db agregator.sqlite3
```

Potencjalne duplikaty firm trafiają do ręcznego review:

```bash
agregator resolution-review \
  --db agregator.sqlite3 \
  --min-score 0.82 \
  --limit 100
```

Ta komenda **niczego nie scala**.

## Weryfikacja oficjalnej WWW

Pipeline rozróżnia finalne źródło rozwiązania domeny:

- `source_candidate` — URL ze źródła oferty, zaakceptowany dopiero po first-party verification,
- `search` — domena znaleziona przez SearchProvider i zweryfikowana,
- `known_url` — URL jawnie przekazany do `scan-url`.

`website_resolution_source` przechowuje konkretne provenance, np. `official_feed.adresWww` albo `brave`. Każda `WebsiteVerificationAttempt` ma własne `origin` i `source`, więc audit zachowuje także kandydatów odrzuconych przed znalezieniem poprawnej domeny.

```text
source website candidates
  -> first-party verification
  -> jeśli brak sukcesu: search
  -> first-party verification
  -> crawl kontaktów
```

## Kontrolowany benchmark end-to-end

Najpierw można sprawdzić konfigurację bez wypisywania wartości sekretów:

```bash
agregator-benchmark preflight \
  --sources olx,jooble,adzuna \
  --strict
```

Pełny workflow:

```bash
agregator-benchmark run \
  --db benchmark/benchmark.sqlite3 \
  --output-dir benchmark/run \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100 \
  --enrichment-batch-size 25 \
  --max-enrichment-companies 1000
```

Workflow wykonuje:

```text
collection
  -> Company Resolution
  -> enrichment
  -> website verification
  -> contact crawl/classification
  -> benchmark report
  -> dataset export
  -> offline website/contact evidence
  -> ground-truth templates
```

Opcja `--strict` ustawia kod wyjścia `2`, jeśli nie osiągnięto targetu albo enrichment nie został domknięty. `benchmark_run_manifest.json` przechowuje `readiness` i listę blockerów. `ready_for_manual_labeling=true` oznacza gotowość do ręcznego labelingu, a nie przejście quality gate.

Szczegóły: [`docs/BENCHMARK_RUN.md`](docs/BENCHMARK_RUN.md).

## Ground truth i quality gate

Pakiet etykiet:

```bash
agregator export-quality-labels \
  --db agregator.sqlite3 \
  --output-dir benchmark/labels \
  --job-limit 1000 \
  --company-limit 1000 \
  --contact-limit 1000
```

Postęp ręcznego labelingu:

```bash
agregator-benchmark status \
  --label-dir benchmark/labels \
  --strict
```

Po kompletnym oznaczeniu można uruchomić zintegrowaną ewaluację:

```bash
agregator-benchmark evaluate \
  --db agregator.sqlite3 \
  --label-dir benchmark/labels \
  --fail-on-error
```

Niskopoziomowy quality gate pozostaje dostępny:

```bash
agregator quality-gate \
  --db agregator.sqlite3 \
  --resolution-truth benchmark/labels/company_resolution_truth.csv \
  --website-truth benchmark/labels/website_resolution_truth.csv \
  --contact-truth benchmark/labels/contact_classification_truth.csv \
  --fail-on-error
```

Domyślne progi:

- Company Resolution F1 >= 0.95,
- Website Resolution F1 >= 0.95,
- Contact decision macro F1 >= 0.90.

`website_resolution_truth.csv` zawiera latest verification provenance, dzięki czemu można powiązać etykietę z zachowanymi snapshotami strony. Ewaluator kontaktów raportuje również `decision_by_kind` z osobnymi metrykami dla `email` i `form`.

## Eksport Faro — schema v7

```bash
agregator export-dataset \
  --db agregator.sqlite3 \
  --output-dir export/faro
```

Powstają:

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

`website_page_snapshots.csv` jest spłaszczonym offline evidence z audit trailu. Zawiera także snapshoty odrzuconych `WebsiteVerificationAttempt`, hash SHA-256, URL, status HTTP, excerpt oraz provenance próby. Nie wymaga ponownego crawlowania strony podczas późniejszego labelingu.

`contact_evidence_snapshots.csv` przechowuje immutable wersje treści dowodu. `contact_evidence_observations.csv` zapisuje każdą obserwację w konkretnym `website_verification_run_id` razem z decision/purpose/confidence i flagą `snapshot_changed`, dzięki czemu ponowne wykrycie kanału można odróżnić od rzeczywistej zmiany evidence.

## Kontakty i evidence

Crawler priorytetyzuje first-party ścieżki takie jak `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza`.

Ekstraktor wykorzystuje widoczny tekst oraz bezpieczne sygnały strukturalne formularza, m.in. `aria-label`, `name`, `id`, `placeholder`, action/method i nazwy kontrolek. Kanonikalizacja URL usuwa fragmenty, domyślne porty i znane parametry trackingowe, ale zachowuje parametry funkcjonalne.

- `GREEN` — mocny publiczny sygnał zgodny z celem,
- `REVIEW` — wymaga ręcznej oceny,
- `IGNORE` — kanał nieodpowiedni.

Sama obecność e-maila, rola w local-part albo checkbox informacji handlowej nie oznacza automatycznie `GREEN`.

```bash
agregator green --db agregator.sqlite3 --limit 100
agregator export-green --db agregator.sqlite3 --output green.csv
```

## Dokumentacja

- plan: [`docs/PLAN.md`](docs/PLAN.md),
- status wdrożenia: [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md),
- benchmark end-to-end: [`docs/BENCHMARK_RUN.md`](docs/BENCHMARK_RUN.md).

## Zasady projektu

1. Publiczne dane i publiczne strony.
2. Brak omijania logowania, CAPTCHA, paywalli i kontroli dostępu.
3. Każdy wynik kontaktowy ma provenance/evidence.
4. Sama obecność e-maila nie oznacza `GREEN`.
5. Fuzzy Company Resolution pozostaje REVIEW-only.
6. Identyczny NIP/REGON nie powoduje automatycznego merge bez zwalidowanej reguły.
7. Źródłowy URL firmy nie jest automatycznie uznawany za oficjalną domenę.
8. Quality gate opiera się na ręcznie oznaczonym ground truth.
9. Outreach i automatyczna wysyłka wiadomości są poza zakresem repo.
