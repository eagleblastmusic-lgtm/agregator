# P10 — real-source validation

## Cel

Po zatrzymaniu rollout na 19 adapterach P10 odpowiada za stabilność i jakość istniejącego pipeline, a nie za zwiększanie liczby portali.

Walidacja obejmuje:

```text
source health
    + current job/company state
    + company identity quality
    + source provenance
    + employer website candidates
    + official website verification
    + linked companies with GREEN contacts
```

## Raport

```bash
agregator-validate report \
  --db agregator.sqlite3 \
  --output validation/p10.json \
  --markdown validation/p10.md
```

Raport obejmuje wszystkie adaptery z aktualnego registry, również te, które nie były jeszcze uruchomione w danej bazie.

Dla każdego źródła pokazuje m.in.:

- tryb dostępu i wymagane zmienne środowiskowe,
- `healthy` / `failing` / `unexercised` z historii `source_runs`,
- liczbę bieżących ofert i firm,
- liczbę powiązanych firm ze zweryfikowaną WWW,
- liczbę powiązanych firm z kanałem `GREEN`,
- source-provided website verification,
- średnią pewność nazwy firmy i Company Resolution,
- provenance identifierów i website candidates,
- historię website verification attempts.

Per-source WWW/GREEN są diagnostyką firm powiązanych z ofertami danego źródła. Ta sama firma może występować w kilku portalach, dlatego wartości per-source mogą się nakładać i nie należy ich sumować jako unikalnych firm globalnych.

## Real smoke

Publiczne adaptery można sprawdzić workflow `Public Scraper Smoke` albo lokalnie:

```bash
agregator-scrape run \
  --sources all \
  --pages-per-source 1 \
  --db validation/smoke.sqlite3 \
  --fresh \
  --strict
```

Po smoke należy wykonać P11/enrichment, a następnie wygenerować raport P10 na tej samej bazie. Dzięki temu raport obejmie cały przepływ od oferty do kanału B2B.

## Co jest sygnałem problemu

Raport nie przyznaje źródłom arbitralnych ocen ani punktów. Do diagnostyki służą konkretne obserwacje:

- `state=failing` — ostatni zapisany run źródła zakończył się błędem,
- `unexercised` — brak historii uruchomień w tej bazie,
- zero current jobs po poprawnym runie — wymaga sprawdzenia listingu/paginacji,
- niski company-name/resolution confidence — problem z identyfikacją pracodawcy,
- niski website-candidate coverage — portal dostarcza mało employer clues,
- niski linked website rate — problem na etapie official website resolution,
- niski GREEN rate — może wynikać z charakteru firm lub z problemu crawl/classification i wymaga evidence review.

## Zasada

Celem P10 jest wykrywanie regresji oraz mierzenie jakości realnego pipeline. Rozbudowa katalogu ponad obecne 19 adapterów pozostaje poza bieżącym zakresem, chyba że dane walidacyjne pokażą konkretną lukę biznesową.
