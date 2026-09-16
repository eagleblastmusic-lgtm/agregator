# Faro Employer Discovery Engine — implementation status

Aktualny PR obejmuje funkcjonalne baseline'y M0–M4, warstwę pomiarową do realnego benchmarku oraz osobny collection smoke poprzedzający pełny enrichment.

Szczegóły planu: [`PLAN.md`](PLAN.md). Collection smoke: [`COLLECTION_SMOKE.md`](COLLECTION_SMOKE.md). Pełny benchmark: [`BENCHMARK_RUN.md`](BENCHMARK_RUN.md).

## Gotowe baseline'y

- **M0** — crawler first-party, evidence, GREEN/REVIEW/IGNORE, CLI i testy.
- **M1** — OLX, Jooble, Adzuna, Careerjet Publisher API, ePraca WebService, source registry, resumowalne runy, katalog 91 źródeł, round-robin collector, overlap/exclusivity oraz diagnostyka identity/provenance per source.
- **M2** — konserwatywny Company Resolution, aliasy/lokalizacje, metody/confidence, jawne identyfikatory pracodawcy, konflikty NIP/REGON/KRS, fuzzy REVIEW-only, ground truth i pairwise precision/recall/F1.
- **M3** — ranking wyników wyszukiwarki, źródłowe kandydatury WWW, first-party identity verification, search fallback, strukturalne provenance rozwiązania domeny, JSON-LD Organization i audit każdej próby.
- **M4 foundations** — `sitemap.xml`, priorytety stron kontakt/B2B, obfuskowane e-maile, semantyka formularzy, immutable contact/page evidence z SHA-256 oraz timeline obserwacji evidence.
- **Quality benchmark** — osobne ground truth i ewaluatory dla Company Resolution, domen i kontaktów, wspólny quality gate oraz diagnostyka `decision_by_kind`.
- **Employer Discovery Score** — niezależny biznesowy ranking 0–100.
- **Collection smoke** — realne sprawdzenie źródeł bez Brave/enrichmentu, z source-health gate i datasetem.
- **Controlled benchmark workspace** — collection → enrichment → report → dataset → offline evidence → deterministyczny sampling → blind primary labels + prediction reference.

## Źródła ofert i access policy

Zarejestrowane adaptery:

```text
olx
jooble
adzuna
careerjet
epraca
```

`SourceRegistry` przechowuje `access_mode`, `experimental` i opcjonalną notatkę operacyjną:

```text
jooble     partner_api
adzuna     partner_api
careerjet  partner_api
epraca     official_partner_feed
olx        public_web_endpoint + experimental
```

Careerjet i ePraca wymagają prawidłowej konfiguracji partnera/integratora. Repo nie tworzy sztucznych danych wymaganych przez te usługi i nie obchodzi uwierzytelniania. Obecny adapter OLX wymaga jawnego `--allow-experimental-sources` w kontrolowanych runach.

Benchmark mierzy źródła na niezależnych osiach zamiast redukować je do jednego arbitralnego score:

```text
wolumen
exclusivity / overlap
identity quality
jawne employer evidence
stabilność runów
czas / koszt runtime
```

## Collection smoke przed benchmarkiem 1000

Dostępny jest osobny entrypoint:

```bash
agregator-collect sources
agregator-collect preflight --sources jooble,adzuna --strict
agregator-collect run \
  --db benchmark/collection.sqlite3 \
  --output-dir benchmark/collection \
  --sources jooble,adzuna \
  --target-jobs 100 \
  --max-rounds 10 \
  --strict
```

Collection-only preflight nie wymaga SearchProvider ani `BRAVE_SEARCH_API_KEY`.

Collector kończy pełną rundę round-robin przed sprawdzeniem `target_jobs`, dlatego szybkie pierwsze źródło nie może zakończyć rundy zanim pozostałe adaptery zostaną sprawdzone. Końcowa liczba rekordów może przez to lekko przekroczyć target.

`--strict` wymaga jednocześnie:

```text
collection_target_reached = true
source_health_ready = true
```

Source health blokuje readiness, gdy żądane źródło nie wykonało udanego runu, zostało disabled albo wykonało run, ale nie zwróciło żadnej oferty. Przejściowe błędy, po których źródło później działa, pozostają widoczne w `sources_with_errors` bez automatycznego blokowania runu.

`collection_run_manifest.json` schema v2 przechowuje m.in. `unexercised_sources`, `disabled_sources`, `sources_without_jobs`, `sources_with_errors` i listę blockerów.

Manualny workflow `.github/workflows/collection-smoke.yml` tworzy artifact z preflightem, bazą, raportem, datasetem v8 i czytelnym GitHub Step Summary. Nie uruchamia się na push/PR.

## Company Resolution

Każda oferta zachowuje m.in. `company_resolution_method`, `company_resolution_confidence`, provenance i confidence źródła nazwy pracodawcy.

Jawne `CompanyIdentifier` są normalizowane i zapisywane do `company_identifiers`. Rozpoznawane są m.in. NIP, REGON i KRS. Konflikt tego samego identyfikatora pomiędzy różnymi `company_id` trafia do REVIEW i nie powoduje automatycznego merge.

`company_identifier_observations` zachowuje provenance każdej obserwacji jako `job_source + evidence_source`. Dzięki temu dwa portale, które dostarczyły ten sam NIP, pozostają osobno widoczne w diagnostyce źródeł.

Fuzzy similarity pozostaje warstwą REVIEW-only do czasu walidacji na rzeczywistym ground truth.

## Oficjalna WWW i provenance

`JobPosting` może zawierać `CompanyWebsiteCandidate`. Kandydat źródłowy nie jest przyjmowany w ciemno — przechodzi ten sam first-party identity verifier co wynik wyszukiwarki.

Finalne rozwiązanie domeny zapisuje:

```text
website_resolution_origin = source_candidate | search | known_url
website_resolution_source = np. official_feed.adresWww | brave | scan_known_website
```

Każda `WebsiteVerificationAttempt` ma również `origin` i `source`, dlatego audit może odtworzyć sekwencję od odrzuconego URL-u ze źródła do zaakceptowanej domeny z search fallback.

`company_website_candidate_observations` zachowuje osobno `job_source` i `evidence_source` każdej źródłowej kandydatury WWW. Benchmark mierzy finalny origin/source, acceptance/rejection źródłowych kandydatur oraz search fallback po odrzuceniu.

## Audit trail

`website_verification_runs` jest append-only i przechowuje finalny outcome, resolution provenance, search candidates, wszystkie sprawdzone `WebsiteVerificationAttempt`, scanned pages i page snapshots.

`contact_evidence_snapshots` przechowuje immutable evidence z SHA-256. `contact_evidence_observations` zapisuje kolejne obserwacje kanału i wiąże je z konkretnym website verification runem oraz snapshotem. `snapshot_changed` rozróżnia recrawl od faktycznej zmiany evidence.

`website_page_snapshots.csv` obejmuje także odrzucone kandydatury domen, dzięki czemu ręczny audyt nie wymaga późniejszego ponownego crawlowania.

## Dataset Faro — schema v8

`agregator export-dataset` generuje:

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

Dwa pliki observations źródłowych danych zachowują pełne `job_source + evidence_source`, więc provenance NIP/REGON/WWW jest audytowalne także poza SQLite. `manifest.json` raportuje liczniki i parse errors.

## Kontrolowany benchmark end-to-end

Pełny benchmark korzysta z osobnego entrypointu:

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
  --label-sampling-seed faro-ground-truth-v1
```

Pełny benchmark wymaga SearchProvider/Brave, ponieważ wykonuje website discovery i enrichment. Jest resumowalny: jeśli baza ma już target kolekcji, może kontynuować enrichment bez ponownego wymuszania live source smoke. Source-health gate jest celowo osobnym etapem `agregator-collect`.

Workflow tworzy `collection.json`, `enrichment.json`, `benchmark_report.json`, dataset schema v8, pakiet etykiet, `labels/sampling_manifest.json`, `labels/prediction_reference/` i `benchmark_run_manifest.json` schema v5.

`agregator-benchmark source-diagnostics` zwraca sekcje `identity` i `provenance`; te same metryki są również częścią kanonicznego `benchmark_report.json`.

## Ground truth, sampling i blind labeling

Pakiet labelingu obejmuje:

```text
company_resolution_truth.csv
website_resolution_truth.csv
contact_classification_truth.csv
sampling_manifest.json
prediction_reference/*
```

Próbka jest deterministycznie warstwowana. Company Resolution rezerwuje część budżetu na pairwise anchors. Główne `*_truth.csv` są blind-primary; predykcje systemu trafiają do `prediction_reference/` i mogą zostać ujawnione przez `label-reference` dopiero po zapisaniu niezależnego truth dla wiersza.

Quality gate mierzy:

- Company Resolution: pairwise precision/recall/F1,
- Website Resolution: precision/recall/F1, accuracy i wrong-domain,
- Contact Classification: confusion matrix, per-class metrics, macro F1 i diagnostykę osobno dla `email` i `form`.

Domyślne progi:

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

## Najbliższy gate

Najbliższa sekwencja produktu:

```text
CI GREEN
  -> collection smoke 50–100 ofert
  -> sprawdzenie source health / identity / provenance
  -> pełny benchmark 1000 ofert
  -> enrichment
  -> dataset v8 + immutable evidence
  -> blind ground truth
  -> quality gate
  -> kalibracja na podstawie błędów
```

Dopiero po tym należy decydować o M5 (PostgreSQL/API), M7 (kolejne źródła) i rozszerzaniu automatycznych reguł identity/contact acceptance.

## Granice automatyzacji

- tylko publicznie dostępne dane i autoryzowane źródła partnerskie/API,
- brak obchodzenia logowania, CAPTCHA, paywalli i kontroli dostępu,
- fuzzy Company Resolution bez auto-merge,
- konflikt NIP/REGON/KRS bez auto-merge,
- źródłowy URL jest kandydatem, nie automatycznie oficjalną domeną,
- integracje partnerskie wymagają prawidłowej autoryzacji,
- źródła eksperymentalne wymagają jawnego opt-in,
- formularz/checkbox marketingowy jest sygnałem do REVIEW, nie zgodą na outreach,
- quality gate wymaga ręcznie oznaczonego ground truth,
- prediction-reference nie powinien być używany podczas primary labeling,
- outreach i automatyczna wysyłka wiadomości pozostają poza zakresem repo.
