# Faro — diagnostyczny overlap i jakość źródeł ofert

Benchmark raportuje heurystyczny overlap ofert pomiędzy źródłami oraz job-level identity quality. Celem jest odpowiedź na dwa osobne pytania: czy kolejne integracje wnoszą nowe oferty oraz jak dobre dane o firmie dostarczają.

## Ważne ograniczenie

Metryka overlapu **nie jest produkcyjnym deduplikatorem ofert** i nie powinna być używana do automatycznego scalania rekordów.

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
by_source
identity_quality
pairwise
```

`cross_source_shared_fingerprints` oznacza liczbę unikalnych fingerprintów występujących w co najmniej dwóch źródłach.

`cross_source_shared_fingerprint_rate` to ich udział w całej puli unikalnych fingerprintów.

## Wartość pokrycia pojedynczego źródła

`by_source` pokazuje, ile treści danego źródła jest ekskluzywne względem wszystkich pozostałych źródeł w benchmarku:

```text
source
fingerprints
exclusive_fingerprints
shared_fingerprints
exclusive_rate
shared_rate
```

`exclusive_fingerprints` to fingerprinty obserwowane tylko w tym jednym źródle. `exclusive_rate` jest więc prostą diagnostyką marginalnej wartości pokrycia źródła. `shared_rate` pokazuje odwrotnie, jaka część jego fingerprintów pojawia się także gdzie indziej.

## Job-level identity quality per source

`identity_quality` jest liczona wyłącznie z pól zapisanych wraz z ofertą, dzięki czemu późniejszy enrichment firmy nie jest błędnie przypisywany portalowi źródłowemu.

Dla każdego źródła raport obejmuje:

```text
jobs
companies
company_to_job_ratio
avg_company_name_confidence
avg_company_resolution_confidence
company_name_confidence_ge_070_rate
resolution_confidence_ge_070_rate
city_coverage_rate
description_coverage_rate
resolution_methods
```

To pozwala odróżnić źródło, które daje dużo unikalnych ofert, ale słabą identity, od źródła o mniejszym wolumenie, lecz stabilnej nazwie firmy/lokalizacji i wysokim resolution confidence.

Te metryki nie próbują przypisywać źródłu później znalezionych NIP/REGON/WWW, jeśli nie ma jednoznacznego job-level provenance. Dzięki temu raport nie zawyża jakości źródła na skutek enrichmentu wykonanego z innego kanału.

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

Po benchmarku 1000 realnych ofert źródła można porównywać razem z:

```text
source_job_counts
source_run_metrics
source_overlap.by_source
source_overlap.identity_quality
company identifiers coverage
website candidate coverage
error rate
request/runtime cost
```

Źródło o dużej liczbie ofert, ale bardzo wysokim overlapie i słabej jakości identity może mieć mniejszą wartość dla Faro niż mniejsze źródło dostarczające unikalne oferty albo lepszą tożsamość pracodawców.

Nie wprowadzamy jeszcze arbitralnego „Source Value Score”. Wagi takiego score powinny wynikać z realnego benchmarku i potrzeb produktu, a nie z założeń przed pomiarem.

## Czego jeszcze nie robimy

Na tym etapie fingerprint nie używa fuzzy matching, embeddingów, opisów ofert ani dat publikacji. To celowe: przed realnym benchmarkiem lepiej mieć prostą, audytowalną metrykę niż zbyt agresywny deduplikator generujący niewidoczne false positives.

Jeśli realne dane pokażą, że fingerprint jest zbyt słaby, następny krok powinien być oparty na ręcznie oznaczonym zbiorze par ofert i osobnym quality gate dla deduplikacji.
