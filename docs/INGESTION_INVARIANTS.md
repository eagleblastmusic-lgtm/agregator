# Faro — invariants pobierania wszystkich źródeł

## Cel

Warstwa agregacji ma **zebrać wszystkie dostępne rekordy ofert z każdego obsługiwanego źródła**. Nie wolno usuwać rekordu tylko dlatego, że podobna lub identyczna oferta występuje w innym portalu.

Przykład:

```text
Portal A
  ACME — Specjalista ds. sprzedaży
  nazwa firmy + miasto

Portal B
  ACME — Specjalista ds. sprzedaży
  nazwa firmy + miasto + NIP + WWW

Portal C
  ACME — Specjalista ds. sprzedaży
  nazwa firmy + inny opis / dodatkowe dane
```

Wszystkie trzy rekordy pozostają zachowane.

## Twarde zasady

1. **Brak cross-source deduplikacji ofert.**
   Ta sama oferta z dwóch lub większej liczby portali jest przechowywana jako osobne rekordy źródłowe.

2. **Company Resolution nie usuwa ofert.**
   Może powiązać wiele rekordów z tym samym `company_id`, ale jest to relacja/grupowanie, a nie deduplikacja danych źródłowych.

3. **Każde źródło zachowuje własne dane.**
   Opis, URL, lokalizacja, identyfikatory firmy i kandydatury WWW pozostają przypisane do konkretnego źródła/provenance.

4. **Różnice między portalami są wartością, nie błędem.**
   Jeżeli jeden portal ma NIP/REGON/WWW lub dodatkowy kontekst, którego nie ma drugi, dane są dodawane do warstwy evidence bez usuwania słabszego rekordu.

5. **Każdy przebieg scrapera jest audytowalny.**
   `job_posting_observations` jest append-only i zapisuje każdą obserwację zwróconą przez collector wraz z pełnym `payload_json`.

6. **`job_postings` to bieżący widok per rekord źródłowy, nie globalny deduplikator.**
   Klucz `(source, source_id)` pozwala aktualizować bieżący stan tego samego rekordu w tym samym portalu. Historia poprzednich wersji pozostaje w `job_posting_observations`.

7. **Overlap służy wyłącznie do diagnostyki.**
   Fingerprinty `firma + stanowisko + miasto` mogą mierzyć nakładanie się źródeł, ale nie wolno używać ich do kasowania lub scalania ofert.

## Docelowy przepływ

```text
WSZYSTKIE OBSŁUGIWANE PORTALE
          │
          ▼
  scraper każdego źródła
          │
          ▼
append-only source observations
          │
          ├─────────────► Portal A record
          ├─────────────► Portal B record
          └─────────────► Portal C record
          │
          ▼
normalizacja / company linking
          │
          ▼
wspólna firma może zebrać evidence
z wielu niezależnych rekordów
          │
          ▼
oficjalna WWW + crawl współpracy/B2B
          │
          ▼
kontakt + evidence + provenance
```

Najważniejsza zasada: **Faro ma maksymalizować zachowanie informacji ze wszystkich baz, a nie minimalizować liczbę rekordów.**
