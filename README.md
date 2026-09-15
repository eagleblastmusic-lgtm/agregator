# Agregator — Faro Employer Discovery Engine

Silnik do budowania bazy firm aktywnie rekrutujących oraz wykrywania ich oficjalnych stron WWW i publicznych kanałów współpracy B2B.

## Główny łańcuch

`oferta pracy -> firma -> oficjalna domena -> crawl strony -> kanał współpracy -> dowód + confidence`

Projekt **nie wysyła wiadomości**, nie omija logowania ani zabezpieczeń portali i nie próbuje pozyskiwać niepublicznych danych. Zapisuje publicznie dostępne informacje oraz źródło, z którego zostały znalezione.

## Aktualny zakres M0/M1

- modele danych dla ofert, firm, kanałów kontaktu i dowodów,
- kontrakt `JobSource` dla wielu portali pracy,
- pierwszy adapter `OlxPublicSource`,
- resumowalne pobieranie stron wyników przez cursor/offset,
- SQLite: `companies`, `job_postings`, `contact_channels`, `source_state`,
- podstawowa deduplikacja firm,
- confidence źródła nazwy firmy,
- wyszukiwanie oficjalnej strony przez wymienny `SearchProvider`,
- opcjonalny provider Brave Search API,
- resolver domeny z oceną dopasowania,
- crawler stron firmowych z limitem stron i obsługą `robots.txt`,
- ekstrakcja e-maili oraz formularzy,
- klasyfikacja kontekstu: `GREEN / REVIEW / IGNORE`,
- wykrywanie fraz typu „propozycje współpracy”, „partnerzy biznesowi”,
  „oferty handlowe”, „dla dostawców”,
- zachowywanie `evidence_url`, `evidence_text` i confidence,
- kolejka firm do enrichmentu z minimalnym confidence tożsamości,
- testy jednostkowe i CI.

## Instalacja

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
```

Opcjonalnie ustaw klucz wyszukiwarki:

```bash
cp .env.example .env
# BRAVE_SEARCH_API_KEY=...
```

## Użycie

### 1. Utworzenie bazy

```bash
agregator db-init --db agregator.sqlite3
```

### 2. Pobranie publicznych ofert OLX Praca

Pierwsza strona:

```bash
agregator collect-olx --db agregator.sqlite3 --pages 1
```

Kolejne uruchomienie wznawia pracę od zapisanego kursora. Aby zacząć od początku:

```bash
agregator collect-olx --db agregator.sqlite3 --pages 2 --fresh
```

Adapter OLX korzysta wyłącznie z publicznego webowego źródła danych. Przed wdrożeniem produkcyjnym sposób dostępu do każdego portalu musi zostać ponownie zweryfikowany technicznie i regulaminowo.

### 3. Podgląd wykrytych firm

```bash
agregator companies --db agregator.sqlite3 --limit 50
```

Firmy, których nazwa pochodzi wyłącznie z niskiej jakości fallbacku, np. nazwy konta osoby prywatnej, dostają niższy `identity_confidence` i domyślnie nie trafiają do automatycznego enrichmentu.

### 4. Znalezienie oficjalnych stron i kanałów B2B

Wymaga `BRAVE_SEARCH_API_KEY`:

```bash
agregator enrich-db --db agregator.sqlite3 --limit 20
```

Domyślnie przetwarzane są firmy z `identity_confidence >= 0.7`.

### 5. Wyniki GREEN

```bash
agregator green --db agregator.sqlite3 --limit 100
```

Każdy wynik zawiera źródło dowodu i tekst kontekstu, w którym kontakt został znaleziony.

### Pojedyncza znana firma

Bez wyszukiwarki — skan znanej domeny:

```bash
agregator scan-url --company "Przykładowa Firma" --url https://example.com
```

Z providerem wyszukiwania:

```bash
agregator discover --company "Przykładowa Firma" --city Gdynia
```

## Ważne ograniczenie adaptera OLX

Nie każda oferta OLX zawiera jednoznaczną nazwę przedsiębiorstwa. Adapter zapisuje provenance nazwy i confidence:

- `company.name` — bardzo wysoki confidence,
- `user.company_name` — wysoki confidence,
- `partner.name` — wysoki/średni confidence,
- `user.name` — niski confidence,
- `contact.name` — bardzo niski confidence.

Dzięki temu imię rekrutera typu „Kazimierz” nie jest automatycznie traktowane jako pewna nazwa firmy i nie jest domyślnie wysyłane do wyszukiwarki domen.

## Dokumentacja

Pełny plan: [`docs/PLAN.md`](docs/PLAN.md).

## Zasady projektu

1. Publiczne dane i publiczne strony.
2. Brak omijania logowania, CAPTCHA, paywalli i ograniczeń dostępu.
3. Każdy wynik kontaktowy musi mieć provenance/evidence.
4. Sama obecność e-maila nie oznacza `GREEN`.
5. Adaptery portali pracy są oddzielone od silnika enrichmentu.
6. Każde źródło przed wdrożeniem produkcyjnym przechodzi przegląd regulaminu i sposobu dostępu.
7. Outreach i automatyczna wysyłka wiadomości są poza zakresem tego repo.
