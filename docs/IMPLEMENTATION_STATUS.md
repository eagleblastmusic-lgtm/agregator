# Faro Employer Discovery Engine — implementation status

Aktualny zakres PR obejmuje M0–M3, fundamenty M4 oraz warstwę pomiarową potrzebną do kontrolowanego benchmarku: enrichment kontaktów, agregację ofert, Company Resolution, dwuetapową weryfikację oficjalnej strony WWW, audyt provenance i ręcznie etykietowane quality gates.

Szczegółowy plan i checkpointy: [`PLAN.md`](PLAN.md).

## Gotowe baseline'y

- M0: crawler + evidence + GREEN/REVIEW/IGNORE.
- M1: OLX, Jooble, Adzuna, Careerjet Publisher API i oficjalny ePraca WebService, source registry, resumowalne runy, katalog 91 źródeł, pełny bundle eksportowy dla Faro oraz kontrolowany `benchmark-collect` round-robin.
- M2: konserwatywny Company Resolution v1, aliasy/lokalizacje, metody/confidence, ground truth, pairwise precision/recall/F1, fuzzy REVIEW bez automatycznego merge oraz warstwa jawnych identyfikatorów pracodawcy.
- M3: ranking wyników wyszukiwarki + first-party content verification z fallbackiem do kolejnych kandydatów, JSON-LD Organization oraz zapis każdej próby weryfikacji kandydata.
- M4 foundations: `sitemap.xml`, priorytety podstron współpracy/B2B, typowe obfuskowane e-maile, formularze ze zgodą na informacje handlowe, append-only evidence snapshots z SHA-256.
- Quality benchmark: osobne ground truth i ewaluatory dla Company Resolution, wyboru oficjalnej domeny oraz klasyfikacji kontaktów.
- Employer Discovery Score: niezależny od confidence ranking firm na podstawie liczby ofert, liczby źródeł, zweryfikowanej WWW, strony biznesowej, GREEN channel i jakości identity.

## Jawne identyfikatory pracodawcy

`JobPosting` może przenosić źródłowe identyfikatory przedsiębiorstwa wraz z provenance i confidence. Są one zapisywane do `company_identifiers` po przypisaniu oferty do firmy.

Aktualnie rozpoznawane i normalizowane są m.in.:

- `nip` — 10 cyfr,
- `regon` — 9 lub 14 cyfr,
- `krs` — 10 cyfr,
- inne identyfikatory mogą być przechowane jako jawne identyfikatory tekstowe.

ePraca mapuje oficjalne pola `nip` i `regon` z confidence `0.995`. Jeśli ten sam identyfikator pojawi się pod więcej niż jednym aktualnym `company_id`, silnik zapisuje konflikt do warstwy pomiarowej/REVIEW i **nie wykonuje automatycznego merge**. Benchmark raportuje `company_identifiers_total`, `companies_with_identifiers`, `identifier_company_rate` oraz `identifier_conflicts`.

## ePraca — oficjalny WebService integratorski

Adapter `epraca` korzysta z oficjalnego WebService v2 i wymaga wartości `Partner` przypisanej podmiotowi przez MRPiPS. Nie ma żadnego fallbacku omijającego autoryzację.

Wymagana konfiguracja:

```text
EPRACA_PARTNER=<wartość nadana przez MRPiPS>
EPRACA_LANGUAGE=pl
```

oraz dokładnie jedno kryterium:

```text
EPRACA_WOJEWODZTWO=22
```

albo:

```text
EPRACA_JEDNOSTKA=22000
```

albo:

```text
EPRACA_ALL=true
```

Adapter wysyła SOAP POST, rozpoznaje statusy usługi, odczytuje zwracane archiwum ZIP i parsuje pliki JSON z aktywnymi ofertami do wspólnego modelu `JobPosting`. Obsługiwany jest zarówno ZIP osadzony w odpowiedzi SOAP jako base64, jak i bezpośrednia odpowiedź ZIP. Pole `pracodawca` ma wysoki identity confidence, a `identyfikatorOferty`, `stanowisko`, `miejscowosc`, `link`, `dataDodaniaOferty`, `dataAktualizacji`, `nip` i `regon` są mapowane z oficjalnego feedu.

Ze względu na autoryzację, limit wywołań i okna dostępności ePraca nie jest dodawana automatycznie do domyślnego benchmarku. Można ją jawnie podać przez `--sources epraca,...` po uzyskaniu prawidłowej konfiguracji integratora.

## Careerjet Publisher API

Adapter `careerjet` korzysta z oficjalnego endpointu Publisher API v4 i wymaga konfiguracji partnera. Nie wymyśla danych wymaganych przez Careerjet. Do uruchomienia potrzebne są:

```text
CAREERJET_API_KEY
CAREERJET_REFERER
CAREERJET_USER_IP
CAREERJET_USER_AGENT
```

Dodatkowo można ustawić `CAREERJET_LOCALE`, `CAREERJET_KEYWORDS`, `CAREERJET_LOCATION`, `CAREERJET_PAGE_SIZE` i `CAREERJET_SORT`.

Careerjet wymaga, aby `user_ip`, `user_agent` i `Referer` odpowiadały rzeczywistemu kontekstowi użycia Publisher API. Z tego powodu `careerjet` nie został dodany do domyślnej listy automatycznego benchmarku backendowego; powinien być używany tylko wtedy, gdy konkretny scenariusz integracji spełnia warunki konta Publisher.

## Kontrolowany benchmark

```bash
agregator benchmark-collect \
  --db agregator.sqlite3 \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100

agregator benchmark --db agregator.sqlite3
```

`benchmark-collect` działa round-robin i daje każdemu aktywnemu źródłu najwyżej jedną stronę na rundę. Źródła bez wymaganej konfiguracji są wyłączane, a powtarzające się błędy runtime mają limit. `benchmark` raportuje także `source_run_metrics`: success rate, strony, oferty, insert/update, utworzone firmy i czas per source, a także pokrycie i konflikty jawnych identyfikatorów pracodawcy.

## Kluczowe komendy jakościowe

```bash
agregator resolution-review --db agregator.sqlite3 --min-score 0.82 --limit 100

agregator export-quality-labels \
  --db agregator.sqlite3 \
  --output-dir benchmark/labels \
  --job-limit 1000 \
  --company-limit 1000 \
  --contact-limit 1000

agregator evaluate-resolution \
  --db agregator.sqlite3 \
  --path benchmark/labels/company_resolution_truth.csv

agregator evaluate-website \
  --db agregator.sqlite3 \
  --path benchmark/labels/website_resolution_truth.csv

agregator evaluate-contacts \
  --db agregator.sqlite3 \
  --path benchmark/labels/contact_classification_truth.csv

agregator quality-gate \
  --db agregator.sqlite3 \
  --resolution-truth benchmark/labels/company_resolution_truth.csv \
  --website-truth benchmark/labels/website_resolution_truth.csv \
  --contact-truth benchmark/labels/contact_classification_truth.csv \
  --fail-on-error

agregator export-dataset --db agregator.sqlite3 --output-dir export/faro
```

## Co mierzy quality gate

- Company Resolution: pairwise TP/FP/FN/TN oraz precision/recall/F1.
- Oficjalna WWW: poprawny host, błędny host, false positive, false negative, precision/recall/F1 i accuracy. `__none__` oznacza ręcznie potwierdzony brak oficjalnej strony.
- Kontakty: macierz pomyłek GREEN/REVIEW/IGNORE, accuracy, per-class precision/recall/F1, macro F1 oraz opcjonalną zgodność `purpose`.

Domyślne progi `quality-gate` to:

- Company Resolution F1 >= 0.95,
- Website Resolution F1 >= 0.95,
- Contact decision macro F1 >= 0.90.

Progi są parametrami CLI i przed zamrożeniem produkcyjnym powinny zostać potwierdzone na realnym, ręcznie oznaczonym benchmarku.

## Audit trail i eksport Faro

Każdy enrichment zapisuje append-only `website_verification_runs`, również gdy żaden kandydat nie został zaakceptowany. Rekord przechowuje ranking wyszukiwarki, wszystkie rzeczywiście sprawdzone kandydaty wraz z wynikiem weryfikacji, sygnały, odwiedzone strony i finalny confidence.

Kontaktowe evidence jest snapshotowane do `contact_evidence_snapshots`. Każdy snapshot ma pełny tekst dowodu, URL, signal, timestamp i SHA-256; identyczny snapshot nie jest dublowany.

`export-dataset` schema v3 eksportuje:

- `companies.csv`,
- `job_postings.csv`,
- `company_identifiers.csv`,
- `contact_channels.csv`,
- `website_verification_runs.csv`,
- `contact_evidence_snapshots.csv`,
- `manifest.json`.

## M4 — wdrożone fundamenty crawler/classifier v2

- `sitemap.xml` i ograniczona obsługa sitemap index,
- priorytety `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza`,
- rekonstrukcja publicznych adresów typu `wspolpraca [at] firma [dot] pl` i `partnerzy (małpa) firma.pl`,
- wykrywanie formularzy z checkboxem/frazą zgody na informacje handlowe jako `SALES / REVIEW`, nigdy automatycznie GREEN,
- JSON-LD `Organization`/`Corporation`/`LocalBusiness` jako dodatkowy sygnał tożsamości oficjalnej WWW,
- trwały audit trail prób weryfikacji WWW,
- immutable evidence hash dla znalezionych kanałów.

M4 nie jest jeszcze zamknięte. Do dalszego rozwinięcia pozostają m.in. bogatsza semantyka formularzy, dodatkowe warianty obfuskacji, snapshot/hash całych stron oraz kalibracja classifiera na realnym ground truth.

## Cel najbliższego benchmarku

Próbka 1000 ofert ma dostarczyć danych do kalibracji:

- precision/recall/F1 Company Resolution,
- jakości fuzzy REVIEW,
- pokrycia i konfliktów jawnych identyfikatorów firm,
- precision/recall wyboru oficjalnej domeny,
- udziału firm z poprawnym enrichmentem,
- jakości GREEN/REVIEW/IGNORE,
- rozkładu Employer Discovery Score,
- kosztu/czasu per źródło i per firma.

## Granice automatyzacji

- fuzzy podobieństwo nazw nie scala firm automatycznie,
- identyczny NIP/REGON znaleziony pod różnymi `company_id` trafia do konfliktu/REVIEW zamiast automatycznego merge,
- domena WWW jest mocnym sygnałem REVIEW, ale auto-merge wymaga wcześniejszej walidacji na ground truth,
- formularz ze zgodą marketingową jest sygnałem REVIEW, a nie zgodą na automatyczny outreach,
- quality gate nie zastępuje ręcznego labelingu — mierzy jakość względem etykiet,
- źródła partnerskie/API nie są zastępowane obchodzeniem uwierzytelniania lub zabezpieczeń,
- adaptery partnerskie są uruchamiane tylko w kontekście zgodnym z wymaganiami danego partnera,
- outreach pozostaje poza zakresem repo.
