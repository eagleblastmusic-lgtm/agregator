# Faro Employer Discovery Engine — implementation status

Aktualny PR obejmuje M0–M3, fundamenty M4 oraz kompletną warstwę pomiarową do kontrolowanego benchmarku i ręcznego ground truth.

Szczegóły planu: [`PLAN.md`](PLAN.md). Uruchomienie benchmarku: [`BENCHMARK_RUN.md`](BENCHMARK_RUN.md).

## Gotowe baseline'y

- **M0** — crawler first-party, evidence, GREEN/REVIEW/IGNORE, CLI i testy.
- **M1** — OLX, Jooble, Adzuna, Careerjet Publisher API, ePraca WebService, source registry, resumowalne runy, katalog 91 źródeł, round-robin collector.
- **M2** — konserwatywny Company Resolution, aliasy/lokalizacje, metody/confidence, jawne identyfikatory pracodawcy, konflikty NIP/REGON/KRS, fuzzy REVIEW-only, ground truth i pairwise precision/recall/F1.
- **M3** — ranking wyników wyszukiwarki, źródłowe kandydatury WWW, first-party identity verification, search fallback, strukturalne provenance rozwiązania domeny, JSON-LD Organization i audit każdej próby.
- **M4 foundations** — `sitemap.xml`, priorytety stron kontakt/B2B, obfuskowane e-maile, semantyka formularzy, immutable contact/page evidence z SHA-256 oraz timeline obserwacji evidence.
- **Quality benchmark** — osobne ground truth i ewaluatory dla Company Resolution, domen i kontaktów, wspólny `quality-gate` oraz diagnostyka `decision_by_kind`.
- **Employer Discovery Score** — niezależny biznesowy ranking 0–100.
- **Controlled benchmark workspace** — end-to-end collection → enrichment → report → dataset → offline evidence → deterministycznie próbkowane label templates.

## Źródła ofert

Zarejestrowane adaptery:

```text
olx
jooble
adzuna
careerjet
epraca
```

Careerjet i ePraca wymagają prawidłowej konfiguracji partnera/integratora. Repo nie tworzy sztucznych danych wymaganych przez te usługi i nie obchodzi uwierzytelniania.

## Company Resolution

Każda oferta zachowuje m.in. `company_resolution_method`, `company_resolution_confidence`, provenance i confidence źródła nazwy pracodawcy.

Jawne `CompanyIdentifier` są normalizowane i zapisywane do `company_identifiers`. Rozpoznawane są m.in. NIP, REGON i KRS. Konflikt tego samego identyfikatora pomiędzy różnymi `company_id` trafia do REVIEW i nie powoduje automatycznego merge.

Fuzzy similarity pozostaje warstwą REVIEW-only do czasu walidacji na rzeczywistym ground truth.

## Oficjalna WWW i provenance

`JobPosting` może zawierać `CompanyWebsiteCandidate`. Kandydat źródłowy nie jest przyjmowany w ciemno — przechodzi ten sam first-party identity verifier co wynik wyszukiwarki.

Finalne rozwiązanie domeny zapisuje:

```text
website_resolution_origin = source_candidate | search | known_url
website_resolution_source = np. official_feed.adresWww | brave | scan_known_website
```

Każda `WebsiteVerificationAttempt` ma również `origin` i `source`, dlatego audit może odtworzyć sekwencję np.:

```text
błędny URL ze źródła
  -> rejected
  -> Brave search
  -> poprawna domena
  -> accepted
```

Benchmark mierzy zarówno finalny origin/source, jak i acceptance/rejection źródłowych kandydatur oraz search fallback po odrzuceniu.

## Audit trail

`website_verification_runs` jest append-only i przechowuje:

- finalny outcome,
- `resolution_origin` / `resolution_source`,
- search candidates,
- wszystkie rzeczywiście sprawdzone `WebsiteVerificationAttempt`,
- scanned pages,
- `page_snapshots_json`.

`contact_evidence_snapshots` przechowuje immutable evidence kontaktowe z SHA-256. `contact_evidence_observations` zapisuje kolejne obserwacje kanału i wiąże je z konkretnym website verification runem oraz snapshotem. `snapshot_changed` rozróżnia zwykły recrawl od faktycznej zmiany evidence.

Dodatkowy exporter spłaszcza page snapshots do `website_page_snapshots.csv`, obejmując również odrzucone kandydatury domen. Dzięki temu ręczny audyt nie wymaga późniejszego ponownego crawlowania strony.

## Dataset Faro — schema v7

`agregator export-dataset` generuje:

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

`website_page_snapshots.csv` zawiera URL, status HTTP, SHA-256, excerpt tekstu, attempt/final scope i provenance próby. `contact_evidence_observations.csv` tworzy historię zmian decyzji/purpose/confidence i evidence. `manifest.json` raportuje liczby rekordów i parse errors.

## Kontrolowany benchmark end-to-end

Po instalacji dostępny jest osobny entrypoint:

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

Workflow tworzy `collection.json`, `enrichment.json`, `benchmark_report.json`, dataset schema v7, pakiet etykiet, `labels/sampling_manifest.json` i `benchmark_run_manifest.json`.

Manifest zawiera `readiness`:

- `collection_target_reached`,
- `enrichment_complete`,
- `dataset_exported`,
- `ground_truth_templates_generated`,
- `ready_for_manual_labeling`,
- `manual_ground_truth_required`,
- `blockers`.

`--strict` zwraca kod wyjścia 2, jeśli target nie został osiągnięty albo enrichment nie został w pełni domknięty. Nie zastępuje to quality gate — oznacza tylko techniczną gotowość do ręcznego labelingu.

## Ground truth i sampling

Pakiet labelingu obejmuje:

```text
company_resolution_truth.csv
website_resolution_truth.csv
contact_classification_truth.csv
sampling_manifest.json
```

Label templates nie są już po prostu pierwszymi N rekordami z SQLite. Jeżeli populacja przekracza limit, stosowany jest deterministyczny sampling warstwowy z audytowalnym seedem.

Warstwy obejmują m.in.:

- Company Resolution: źródło + metoda resolution + confidence band,
- Website Resolution: origin + outcome + confidence band + obecność source website candidate,
- Contact Classification: kind + predicted decision + confidence band.

Dla Company Resolution część budżetu próbki jest rezerwowana na pary ofert należące do tego samego przewidywanego `company_id`, aby pairwise precision/recall/F1 nie były liczone na próbce pozbawionej przypadków merge. Pozostały budżet jest rozdzielany proporcjonalnie pomiędzy warstwy.

`sampling_manifest.json` zapisuje population/sample count per stratum, seed i liczbę pairwise anchors. Dzięki temu próbkę można odtworzyć oraz ocenić jej pokrycie przed ręcznym labelingiem.

Website ground truth zawiera dodatkowo `latest_verification_id`, outcome, predicted origin/source, liczbę source website candidates i verification signals. `latest_verification_id` można łączyć z `website_page_snapshots.csv` podczas ręcznego audytu.

Quality gate mierzy:

- Company Resolution: pairwise TP/FP/FN/TN, precision, recall, F1,
- Website Resolution: TP/FP/FN/TN, wrong domain, precision, recall, F1, accuracy,
- Contact classification: confusion matrix, per-class metrics, macro F1 i diagnostykę osobno dla `email` i `form`.

Domyślne progi pozostają:

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

## Najbliższy gate

Następny krok produktu to **realny benchmark 1000 ofert + ręczny ground truth**, a nie dalsze agresywne rozszerzanie reguł automatycznych.

Należy zmierzyć:

- precision/recall/F1 Company Resolution,
- jakość fuzzy REVIEW,
- pokrycie i konflikty jawnych identyfikatorów,
- precision/recall wyboru oficjalnej domeny,
- acceptance/rejection source website candidates,
- search fallback rate po odrzuconym URL źródłowym,
- udział firm z poprawnym enrichmentem,
- jakość GREEN/REVIEW/IGNORE globalnie i per `email`/`form`,
- stabilność evidence przy powtórnych obserwacjach,
- pokrycie warstw w `sampling_manifest.json`,
- rozkład Employer Discovery Score,
- koszt/czas per source i per firma.

## Granice automatyzacji

- tylko publicznie dostępne dane,
- brak obchodzenia logowania, CAPTCHA, paywalli i kontroli dostępu,
- fuzzy Company Resolution bez auto-merge,
- konflikt NIP/REGON/KRS bez auto-merge,
- źródłowy URL jest kandydatem, nie automatycznie oficjalną domeną,
- integracje partnerskie wymagają prawidłowej autoryzacji,
- formularz/checkbox marketingowy jest sygnałem do REVIEW, nie zgodą na outreach,
- quality gate wymaga ręcznie oznaczonego ground truth,
- sampling pomaga zbudować reprezentatywniejszą próbkę, ale nie zastępuje ręcznej walidacji i interpretacji supportu per stratum,
- outreach i automatyczna wysyłka wiadomości pozostają poza zakresem repo.
