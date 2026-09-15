# Agregator — Faro Employer Discovery Engine

Silnik do budowania bazy firm aktywnie rekrutujących oraz wykrywania ich oficjalnych stron WWW i publicznych kanałów współpracy B2B.

## Cel M0

Program ma wykonać łańcuch:

`oferta pracy -> firma -> oficjalna domena -> crawl strony -> kanał współpracy -> dowód + confidence`

M0 **nie wysyła wiadomości**, nie omija logowania ani zabezpieczeń portali i nie próbuje pozyskiwać niepublicznych danych. Zapisuje wyłącznie publicznie dostępne informacje i źródło, z którego zostały znalezione.

## Co już jest w szkielecie

- modele danych dla firm, kanałów kontaktu i dowodów,
- wyszukiwanie oficjalnej strony przez wymienny `SearchProvider`,
- opcjonalny provider Brave Search API,
- resolver domeny z oceną dopasowania,
- crawler stron firmowych z limitem stron i obsługą `robots.txt`,
- ekstrakcja e-maili oraz formularzy,
- klasyfikacja kontekstu: `GREEN / REVIEW / IGNORE`,
- wykrywanie fraz typu „propozycje współpracy”, „partnerzy biznesowi”, „oferty handlowe”, „dla dostawców”,
- zachowywanie `evidence_url`, `evidence_text` i confidence,
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

Bez wyszukiwarki — skan znanej domeny:

```bash
agregator scan-url --company "Przykładowa Firma" --url https://example.com
```

Z providerem wyszukiwania:

```bash
agregator discover --company "Przykładowa Firma" --city Gdynia
```

## Dokumentacja

Pełny plan: [`docs/PLAN.md`](docs/PLAN.md).

## Zasady projektu

1. Publiczne dane i publiczne strony.
2. Brak omijania logowania, CAPTCHA, paywalli i ograniczeń dostępu.
3. Każdy wynik kontaktowy musi mieć provenance/evidence.
4. Sama obecność e-maila nie oznacza `GREEN`.
5. Adaptery portali pracy są oddzielone od silnika enrichmentu.
6. Każde źródło przed wdrożeniem produkcyjnym przechodzi przegląd regulaminu i sposobu dostępu.
