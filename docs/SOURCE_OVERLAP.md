# Faro — diagnostyczny overlap ofert między źródłami

Benchmark raportuje teraz heurystyczny overlap ofert pomiędzy źródłami. Celem jest odpowiedź na pytanie, czy kolejne integracje wnoszą nowe oferty, czy głównie powielają rynek już pokryty przez inne źródła.

## Ważne ograniczenie

Ta metryka **nie jest produkcyjnym deduplikatorem ofert** i nie powinna być używana do automatycznego scalania rekordów.

Fingerprint diagnostyczny powstaje z:

```text
normalize_company_name(company_name_raw)
+
normalize_text(title)
+
normalize_text(city)
```

Dwa rekordy o takim samym fingerprintcie są traktowane jako kandydat na overlap wyłącznie na potrzeby benchmarku. Ten sam pracodawca może publikować kilka różnych ofert o identycznym tytule w tej samej lokalizacji, a źródła mogą mieć różne daty publikacji i zakresy danych.

## Metryki globalne

`benchmark_report.json` zawiera sekcję:

```text
source_overlap
```

z polami:

```text
unique_job_fingerprints
cross_source_shared_fingerprints
cross_source_shared_fingerprint_rate
pairwise
```

`cross_source_shared_fingerprints` oznacza liczbę unikalnych fingerprintów występujących w co najmniej dwóch źródłach.

`cross_source_shared_fingerprint_rate` to ich udział w całej puli unikalnych fingerprintów.

## Metryki par źródeł

Dla każdej pary źródeł, np.:

```text
adzuna|olx
```

raport zawiera:

```text
source_a
source_b
source_a_fingerprints
source_b_fingerprints
shared_fingerprints
union_fingerprints
jaccard
overlap_rate_a
overlap_rate_b
```

Interpretacja:

- `shared_fingerprints` — fingerprinty obecne w obu źródłach,
- `jaccard` — `shared / union`,
- `overlap_rate_a` — jaka część fingerprintów źródła A występuje także w B,
- `overlap_rate_b` — jaka część fingerprintów źródła B występuje także w A.

Asymetryczne overlap rates są szczególnie użyteczne. Przykładowo, jeśli mniejsze źródło ma `overlap_rate_a = 0.95`, ale większe źródło `overlap_rate_b = 0.10`, oznacza to, że niemal cała zawartość mniejszego źródła jest już pokryta przez większe, podczas gdy większe wnosi dużo unikalnej treści.

## Zastosowanie w M1

Po benchmarku 1000 realnych ofert metryka ma pomóc ocenić wartość źródeł razem z:

```text
source_job_counts
source_run_metrics
identity quality
company identifiers coverage
website candidate coverage
error rate
request/runtime cost
```

Źródło o dużej liczbie ofert, ale bardzo wysokim overlapie i słabej jakości identity może mieć mniejszą wartość dla Faro niż mniejsze źródło dostarczające unikalne oferty, NIP/REGON lub oficjalny URL firmy.

## Czego jeszcze nie robimy

Na tym etapie fingerprint nie używa fuzzy matching, embeddingów, opisów ofert ani dat publikacji. To celowe: przed realnym benchmarkiem lepiej mieć prostą, audytowalną metrykę niż zbyt agresywny deduplikator generujący niewidoczne false positives.

Jeśli realne dane pokażą, że fingerprint jest zbyt słaby, następny krok powinien być oparty na ręcznie oznaczonym zbiorze par ofert i osobnym quality gate dla deduplikacji.
