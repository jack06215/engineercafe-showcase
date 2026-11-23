# monkeytype_analysis_console: functional spec

Status: **agreed 2026-11-23**, including every ⚑ item as drafted. Built from
the three interview rounds in `documents/monkeytype-viewer.md`, which git
doesn't track (Q1–Q19 below refer to its questions). Items marked **⚑ review**
were my own choices that the interview didn't settle, or that changed after
it.

The first PR copies the agreed version of this file into
`packages/monkeytype_analysis_console/SPEC.md` (Q16). From then on, that copy
is the one to keep up to date.

---

## 1. What it is

A local Streamlit app for one person. It reads Monkeytype results that the
Surfingkeys `yr` mapping copied as YAML, and shows them on three pages
(Q1, Q6):

- **Result replay** rebuilds Monkeytype's result screen: the stats, the
  per-second chart, and the input history coloured by the burst heatmap.
- **Result analysis** shows the numbers behind one result: checks against
  your goal, speed by heatmap band, typos and key confusions, and speed
  through the test.
- **Progress** shows many results over time, per word list and test type,
  and the words that keep being slow or mistyped.

The console only reads. It never writes a file (Q10). Coaching, such as
choosing what to practise, stays in the `monkeytype-review` skill (Q7).

---

## 2. Scope

### 2.1 In scope

| Area | Feature | Section | PR |
| --- | --- | --- | --- |
| Input | Upload `.yml` files; read a folder of `.yml` files | §4 | 1 |
| Result replay | Headline stats, speed chart, other stats, input history, per-word speed chart, `yr`'s word lists | §6.2 | 1 |
| Result analysis | Result checks, word speed by band, typo classification with a keyboard chart, position in test | §6.3 | 2 |
| Progress | wpm and acc over time, latest vs average, recurring problems | §6.4 | 3 |

### 2.2 Later

- A paste box for YAML (Q9).
- Reading the skill's log directly, or saving results to it (Q9, Q10).
- "Download Vega-Lite spec" buttons and spec checks (Q3, dropped for now by
  the reviewer).
- The result's own theme colours (Q11).
- A practice list (Q7 e).
- Remembering the folder path between sessions (§4.2).

### 2.3 Non-goals

- Linking seconds on the chart to the words typed then. The YAML gives words
  no timestamps, so it could only be an estimate (Q13 e).
- Comparing speeds across word lists or test types.
- Hosting. The app runs on your machine only (Q2).

---

## 3. Runtime and layout

### 3.1 Running

```sh
bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
```

- The `streamlit_app` macro starts Streamlit and opens the browser.
- Streamlit listens on localhost only (`--server.address=localhost`), as
  `//packages/vega_lite_ai:chart_app` does (`BUILD.bazel:62-73`).
- **⚑ review:** if the environment variable `MONKEYTYPE_RESULTS_DIR` is set,
  the results folder box (§4.2) starts with its value, so a shell alias can
  open the console on your folder:

  ```sh
  MONKEYTYPE_RESULTS_DIR=~/workspace/jack06215/monorepo/documents/monkeytype_result \
    bazel run //packages/monkeytype_analysis_console:monkeytype_analysis_console
  ```

### 3.2 Package layout

```text
packages/monkeytype_analysis_console/
├── BUILD.bazel
├── README.md            what the package is for, how to run it
├── SPEC.md              this file
├── main.py              entry point: page config, then ui.render_app()
├── app_pages/
│   ├── replay.py        one line: ui.render_replay_page()
│   ├── analysis.py      one line: ui.render_analysis_page()
│   └── progress.py      one line: ui.render_progress_page()
├── results.py           reading files: model, parsing, folder, duplicates
├── metrics.py           per-result definitions (§5)
├── typos.py             keyboard model and typo classifier (§7)
├── progress.py          many-result definitions: trends, recurring problems
├── charts.py            Altair charts (§6.5)
├── history_html.py      the input history as HTML (§6.6)
├── palette.py           the fixed colours (§6.7)
├── ui.py                Streamlit: sidebar and the three pages
├── fixtures.py          test fixtures (testonly)
├── testdata/            fixture files (§9.1)
└── test_*.py            one test file per module, plus test_ui.py
```

**⚑ review, changed from the interview's defaults:** the pages are files,
not page functions. `AppTest.switch_page` switches only to page files
(`streamlit/testing/v1/app_test.py:803-845`), and `test_ui` needs to open each
page. Each page file is one line, like `main.py`, so the lint targets still
check all the code in `ui.py`.

The folder is `app_pages/`, not `pages/`. A folder named `pages/` next to the
entry point turns on Streamlit's older pages-folder mode
(`streamlit/runtime/pages_manager.py:60-63`). In that mode a rerun runs only
the page file, so the sidebar, which the entry point draws, disappears.

`results.py`, `metrics.py`, `typos.py` and `progress.py` don't import
Streamlit, so they can be tested without it.

### 3.3 Dependencies

`streamlit` 1.67.0, `altair` 6.3.0, `pandas` 3.1.1 and `pyyaml` 6.0.3, all
pinned already. Nothing new.

---

## 4. Input

### 4.1 Format

The input is the YAML that `yr` writes, as described in the interview's
findings ("The input: what `yr` copies"). Facts this spec relies on:

- A file holds one or more documents. Each document starts with `---`.
- `detail.wpm` and `detail.raw` are always in wpm. `yr` reads the wpm value
  even when Monkeytype shows another unit
  (`dot_config/surfingkeys/index.js:821-823` in the dotfiles repo).
- The chart, the heatmap steps, `words[].wpm` and `result.wpm_threshold` are
  in `detail.unit` (wpm, cpm, wps, cps or wph).
- `steps` is present whenever there is an input history, and `bucket` is on
  every word with a finite speed, even with the heatmap off.

### 4.2 Sources

Both sources feed one set of results. Every page uses the same set.

| Source | How | Lifetime |
| --- | --- | --- |
| Upload (Q9) | A sidebar uploader for `.yml` and `.yaml` files, several at once | The browser tab. A reload clears it. |
| Folder (Q18) | A sidebar text box "Results folder". The console reads every `.yml` and `.yaml` file directly in that folder (not in subfolders), in name order. | The browser tab, or `MONKEYTYPE_RESULTS_DIR` (§3.1) |

Folder rules:

- `~` expands to your home folder. A relative path is read from the folder
  you ran `bazel run` in (`BUILD_WORKING_DIRECTORY`), because `bazel run`
  starts the app in its runfiles folder.
- The console never writes to the folder.
- A folder that doesn't exist, or isn't a folder, gives a warning under the
  box. Uploads still work.
- On each rerun, the console lists the folder again and parses only the
  files whose size or modification time changed. A new `yr` file in the
  folder shows up on the next interaction, with no restart.

### 4.3 Parsing

- Each file is parsed with `yaml.load_all` and `yaml.CSafeLoader` (libyaml is
  in the pinned wheel), falling back to `yaml.SafeLoader`. Parsing is cached
  by file content.
- An empty document is skipped.
- A document is a result when it is a mapping with a `datetime` key and a
  `detail` mapping that has `wpm`. This is the check `analyze.py` makes
  (`analyze.py:214-228`).
- A file with a YAML syntax error, or with a document that isn't a result,
  gets an error that names the file, the document number and, for syntax
  errors, the line. The other documents and files still load. The sidebar
  shows the errors in a collapsed section: "2 files had errors".
- `datetime` loads as a timezone-aware `datetime`. A date with no offset is
  read as local time.
- Unknown keys are ignored, so a newer `yr` with more keys still loads.
- Pasted-text leniency from `analyze.py` (code fences, comments, documents
  without `---`) is not needed: uploads and folders hold files.

### 4.4 The result model

`results.py` turns each document into a frozen dataclass `Result`:

| Field | From | Notes |
| --- | --- | --- |
| `source` | file name and document number | for messages and tooltips |
| `copied_at` | `datetime` | when `yr` copied the result |
| `test`, `language` | `detail` | `language` is `None` in custom mode; shown as "custom" |
| `unit` | `detail.unit` | `"wpm"` when absent |
| `wpm`, `raw`, `acc`, `consistency`, `key_consistency` | `detail` | `float`; `None` when absent |
| `keys`, `chars` | `detail` | small dataclasses; `None` when absent |
| `time`, `afk`, `afk_pct` | `detail` | seconds and percent |
| `typed_time` | `session_time` or `today_time` | the label and the seconds |
| `pb`, `crown` | `detail` | `crown` holds `type` and `text` |
| `heatmap` | `detail.heatmap` | `steps`; `labels` and `colors` are ignored (Q11), see §6.6 |
| `chart` | `detail.chart` | a list of rows `t, wpm, raw, burst, errors`; empty when absent |
| `chart_error` | `detail.chart_error` | text or `None` |
| `words` | `detail.words` | a list of `Word` |
| `flags`, `options`, `tags`, `quote_source` | `other`, `options`, `tags`, `source` | lists of text, or text |
| `wpm_threshold`, `word_list`, `missed_word_list`, `slow_word` | `result` | the lists split on spaces |

`Word` has `i`, `word`, `wpm` (`float`, possibly `inf`), `bucket` (`int` or
`None`), `typed`, `fixed` (0 when absent), `error`, `extra_fixed` (both
`False` when absent), `marks` and `letters` (`None` when absent).

### 4.5 Identity and order

- **Same result:** equal `test`, `language`, `wpm`, `raw`, `acc`,
  `consistency` and `time` (Q19). The console keeps the first one it reads
  and counts the others in the sidebar: "12 results from 3 files, 1
  duplicate skipped".
- Results are ordered by `copied_at`. The picker lists the newest first, and
  Progress plots the oldest first.

---

## 5. Definitions

These are the console's own definitions (Q8), agreed in Q19. Where a
definition uses a speed, the speed is in the result's `unit` unless it says
wpm.

| Term | Definition |
| --- | --- |
| Slow word | Its speed is below the threshold. The threshold starts at the result's `wpm_threshold`, and the slider on the replay page changes it (§6.2). An `inf` speed is never slow. At the starting threshold, the slow words are `yr`'s `slow_word` list. |
| Band | The word's heatmap band, `bucket`, 0 (slowest) to 4 (fastest). Monkeytype puts the band edges at the 15th, 35th, 65th and 85th percentile of the test's word speeds. An `inf` word has no band. |
| Band label | The label Monkeytype shows for the band, rebuilt from `steps`: `<s1`, `s1-(s2−1)`, `s2-(s3−1)`, `s3-(s4−1)`, `s4+`. For steps `[0, 37, 70, 92, 127]` that gives `<37`, `37-69`, `70-91`, `92-126`, `127+`. When two edges are equal, the band is empty and its label is the edge. |
| Mistyped word | It has `typed`, `marks`, `error` or `extra_fixed`. This is `yr`'s rule for `missed_word_list` (`index.js:1042-1044`). |
| Keypresses | `keys.correct + keys.incorrect`. Without `keys`: `chars.correct + chars.incorrect + chars.extra`. Without both: unknown. |
| Aborted result | Fewer than 25 keypresses, or a flag in `other` that contains "too short". The pages show it with an "aborted" flag. Analysis shows only the checks for it, and Progress leaves it out. |
| AFK flag | `afk_pct` over 2. |
| Accuracy goal | 96 to start. The sidebar input changes it, from 0 to 100 in steps of 0.5 (**⚑ review** for the range). The goal is met when `acc` ≥ goal. |
| Time lost to mistakes | `keys.incorrect × 2 × 60 / (raw × 5)` seconds, and at most `time`: each wrong key and its backspace, at your raw speed in wpm. A lower bound, because pauses after a mistake don't count. Unknown without `keys.incorrect` or with `raw` 0. |
| Characters left wrong | `chars.incorrect + chars.extra + chars.missed`. |
| Shift presses | Letters in upper case, plus symbols typed with Shift (`~!@#$%^&*()_+{}\|:"<>?`). |
| Symbols | Characters that are not letters or digits. |
| Position in test | With `n` typed words and `k = n // 3`: the first `k` words, the last `k` words, and the rest as the middle. Under 3 words, one group, "all". |
| Typo categories | The 11 categories of §7. |
| Key confusion | The expected→typed pair of a wrong-key or swapped-letters typo, for example `e→r` or `th→ht`. |
| Trend group | Results with the same word list (`language`, or "custom") and the same `test`. |
| Latest vs average | In a trend group: the latest result against the mean of up to 10 results before it. |
| Recurring problem | A word that is slow (below that result's own `wpm_threshold`) or mistyped in at least 2 of the last 20 results that are not aborted. |

---

## 6. Pages

### 6.1 Sidebar and shared behaviour

The sidebar holds, from the top:

1. The page links (`st.navigation`): Result replay, Result analysis,
   Progress. Result replay is the default page.
1. The uploader and the results folder box (§4.2).
1. The load summary and the error section (§4.3, §4.5).
1. On the two Result pages: the result picker, a select box with the newest
   result first. Each entry reads like
   `2026-11-23 12:20 · words 10 · english 1k · 51.69 wpm`. Both Result pages
   show the same picked result. When the picked result is no longer loaded,
   the picker goes back to the newest.
1. On Result analysis and Progress: the accuracy goal input (§5).

With no results loaded, each page shows one message: upload `yr` files or
enter a results folder in the sidebar.

### 6.2 Result replay (PR 1)

From the top, in Monkeytype's order:

1. **Headline:** wpm and acc, large (`st.metric`). When `pb` is true, a
   "PB" badge with `crown.text`, for example "PB +26.38". When `unit` is not
   wpm, a caption says that the chart and word speeds are in that unit.
1. **Speed chart** (§6.5.1). When `chart_error` is set or there is no
   chart, a message takes its place: "No chart in this result", plus the
   error text.
1. **Other stats**, in one row:
    - test type: `test`, the word list, and `options`, for example
      "words 10 · english 1k";
    - raw;
    - characters as `correct/incorrect/extra/missed`, as Monkeytype shows
      them;
    - consistency, with key consistency under it;
    - time in seconds, with afk seconds and percent under it;
    - the session or today time;
    - flags (`other`), tags and the quote source, when present.

   A missing value shows as "–".
1. **Slow-word threshold slider** (Q13 c), from 0 to the fastest finite word
   speed or `wpm_threshold`, whichever is higher. It starts at
   `wpm_threshold`. Picking another result resets it to that result's
   threshold.
1. **Input history** (§6.6), with the band legend under it.
1. **Per-word speed chart** (§6.5.2).
1. **`yr`'s lists** in `st.code` blocks, which have a copy button:
   "Words", "Missed words" (`missed_word_list`), and "Slow words under N",
   computed at the slider's value. At the starting value it equals `yr`'s
   `slow_word`.

A result with no `words` shows, in place of items 4 to 6: "No input history
in this result. Open it on the result screen before pressing `yr`."

### 6.3 Result analysis (PR 2)

From the top (Q7 a–d):

1. **Result checks:** acc against the goal (met or missed), time lost to
   mistakes (seconds, and percent of `time`), characters left wrong, and the
   flags: Monkeytype's `other`, AFK and aborted. For an aborted result the
   page stops here, with "Nothing else to analyse: fewer than 25
   keypresses."
1. **Word speed by band:** a table with one row per band, labelled with the
   band label. Columns: words, mean speed, mean length, mean Shift presses,
   mean symbols, mistyped words. A last row covers all words. A note under
   the table counts the words that were too fast to measure.
1. **Typos:**
    - a line such as "7 of 100 words mistyped, 9 typos";
    - a table of the categories with their counts and up to 3 examples each,
      in the order of §7;
    - the keyboard chart (§6.5.3);
    - the top 10 key confusions with their counts;
    - a table of the mistyped words: word, first attempt (`typed`), the
      typos found, speed, letters fixed, and whether the word was left wrong.
      A mistyped word without `typed` shows "no first attempt recorded".
1. **Position in test:** a table of the thirds (§5) with words, mean speed
   and mistyped words.

### 6.4 Progress (PR 3)

The page uses every loaded result that is not aborted (Q14).

1. **Test type filter:** a select box of the `test` values, starting at the
   most common one.
1. **One panel per word list** with results of that test type, so each panel
   is one trend group. Each panel has two charts side by side (§6.5.4): wpm
   over time, and acc over time with the goal line. PB results get their own
   mark shape.
1. **Latest vs average:** a table with one row per trend group in the filter:
   word list, test, number of results, the latest date, the latest wpm, acc
   and consistency, and the change against the mean of up to 10 results
   before it. A group with one result says "no earlier results".
1. **Recurring problems:** over the last 20 results of every word list and
   test (**⚑ review**: not filtered). A table of words with how many results
   each was slow in and mistyped in, sorted by the number of results, then
   by word, showing the top 20. Under it, key confusions seen at least twice.

With fewer than 2 results that are not aborted, the page says that progress
needs at least 2 results.

### 6.5 Charts

All charts are Altair, drawn with `st.altair_chart` at the container width
(Q17). There are no download buttons (Q3).

#### 6.5.1 Speed chart

| Part | Drawing |
| --- | --- |
| x | `t` in seconds, including a fractional last row |
| Left y | speed in `unit`, shared by wpm, raw and burst |
| wpm | solid line, main colour, width 3 |
| raw | dashed line, main colour at 60% opacity |
| burst | line with a light fill under it, sub colour |
| Right y | errors, own scale, integer ticks |
| errors | points only, error colour, only at seconds with errors |
| PB line | when `pb` is true, `unit` is wpm, and `crown.text` reads as a signed number: a dashed horizontal line at `wpm − margin`, labelled "previous PB" with its value |
| Legend | wpm, raw, burst, errors |

Interactions (Q13 a, b):

- Clicking a legend entry adds that series to the ones shown, and clicking
  it again removes it. With no series picked, all of them show. This is
  Altair's legend-bound point selection with `toggle` on: Vega-Lite's default,
  where a double-click clears the selection, gave no way back to all series
  in Streamlit's chart. The param sits on the first layer with a colour, the
  burst area, because the legend belongs to that view.
- Hovering the chart shows a vertical rule at the nearest second and a
  tooltip with `t`, wpm, raw, burst and errors.

**⚑ review:** the PB line is left out for units other than wpm, because the
YAML doesn't say which unit `crown.text` uses.

#### 6.5.2 Per-word speed chart

- One bar per word: x = position `i`, y = speed in `unit`, colour = band.
- A dashed horizontal line at the slider's threshold.
- Tooltip: word, speed, band label, first attempt, letters fixed.
- Words with an `inf` speed are left out. A caption counts them.

#### 6.5.3 Keyboard chart

- The US QWERTY keys of §7, one rectangle per key at the key's position,
  with its letter on it.
- Colour: how often the key was the expected key of a wrong-key typo (the
  four "wrong key" categories), on a sequential scale from a neutral colour
  to the error colour. Shifted symbols count on their base key. Shift errors
  and swapped letters don't count.
- Tooltip: the key, the count, and its confusions, for example
  `e→r ×3, e→w ×1`.

#### 6.5.4 Progress charts

- x = `datetime`. y = wpm (one chart) or acc (the other).
- A line through the results, with a point on each. PB results use a
  different point shape.
- On the acc chart, a dashed horizontal line at the goal.
- Tooltip: date and time, test, wpm, acc, consistency, the file it came
  from.

### 6.6 Input history

`history_html.py` builds the input history as one HTML string, shown with
`st.html` (Q12 a).

- The words run in lines that wrap, in a monospace font, separated by
  spaces, in their typed order.
- Each word has its band colour (§6.7). A word with no band (an `inf`
  speed) has the page's text colour.
- The letters come from `letters` when it is present (it includes extras),
  else from `word`. With `marks`, each letter gets its style:

  | Mark | Style |
  | --- | --- |
  | `.` correct | the word's colour |
  | `f` fixed | underlined in the error colour |
  | `x` still wrong | error colour |
  | `+` extra | error colour, struck through |
  | `-` not typed | the word's colour at 40% opacity |

- A slow word (§5) gets a dotted outline (**⚑ review**), so the slider
  visibly changes the history.
- Hovering a word shows its first attempt (`typed`, with `_` for a space as
  `yr` writes it), its speed, the letters fixed, and "left wrong" when
  `error` is true.
- Every word, letter and tooltip text is escaped with `html.escape` before
  it goes into the HTML, because it comes from a file. Styles are inline
  attributes. `st.html` runs no JavaScript.
- Under the history, a legend shows the 5 band colours with the band
  labels.

### 6.7 Palette

`palette.py` holds one fixed palette (Q11). The result's `heatmap.colors`
are ignored.

- **Band colours:** 5 colours from a red (band 0, slowest) through grey
  (band 2) to a blue (band 4, fastest).
- **Chart colours:** main = the band 4 blue, sub = the band 2 grey, error =
  the band 0 red.
- **Contrast:** every colour has a contrast ratio of at least 3:1 (WCAG
  relative luminance) against both of Streamlit's default backgrounds,
  `#FFFFFF` and `#0E1117`. That means a relative luminance between about
  0.12 and 0.30. A test checks this (§9.2).
- **⚑ review:** the exact values, picked in PR 1 within these rules, are
  `#E5484D`, `#D9773E`, `#8B8D98`, `#3B96CA` and `#5B6EE8` for bands 0 to 4.

---

## 7. Typo classification

`typos.py` ports the keyboard model and the typo classifier of `analyze.py`
(`skills/monkeytype-review/scripts/analyze.py:256-433` in the dotfiles repo,
commit `efca31a`) as they are (Q7 c, Q19). After the port, the console's copy
may change without changing the skill's.

- **Input:** a `Word` with `typed`. Words without `typed` have no typos to
  classify.
- **Keyboard:** US QWERTY rows with their offsets, the Shift map and the
  touch-typing finger map, as in `ROWS`, `SHIFTED` and `FINGERS`
  (`analyze.py:256-274`). Neighbour keys are less than 1.3 key widths apart.
- **Alignment:** optimal string alignment of `typed` against `word`. A
  missing or extra key costs 1, a wrong key 1.5, and a swap of two adjacent
  letters 1 (`analyze.py:326-379`). The untyped end of a word may stay
  unmatched under the rules of `analyze.py:393-408`, so a slip that shifts
  the rest of the word reads as one extra or missing key.
- **Categories,** in this order: swapped letters; wrong key: neighbour;
  wrong key: same finger; wrong key: mirror; wrong key: other; Shift error;
  missing letter; extra letter; doubled letter; early space; unfinished
  word.
- **Output per typo:** the category, a short detail such as
  `"e"→"r"` or `extra "s" before "t" (neighbour key)`, and the key confusion
  when there is one.

The keyboard chart (§6.5.3) uses the same key positions.

---

## 8. Edge cases

| Case | Behaviour |
| --- | --- |
| A file is not YAML | Error naming the file and line; other files load (§4.3) |
| A document is not a `yr` result | Error naming the file and document number |
| The same result in two files | Shown once; counted in the load summary |
| A stat is missing | Shown as "–" |
| No `words` | Replay and Analysis say there is no input history; Progress still uses the result's stats |
| No `chart`, or `chart_error` | A message in place of the speed chart |
| `inf` word speed | No band; never slow; "∞" in tables; left out of the per-word chart, with a count |
| `unit` other than wpm | Chart, word speeds and threshold in that unit; headline, Progress and time lost in wpm; no PB line |
| Custom mode | Word list shown as "custom" |
| Aborted result | Flagged; Analysis shows checks only; left out of Progress |
| Folder missing | Warning under the folder box |
| A word with `<`, `&` or quotes | Escaped in the input history |
| One result only | Progress says it needs at least 2 |

---

## 9. Testing

### 9.1 Fixtures

All fixtures are synthetic, built from the one real result (Q15).

- `testdata/real_words10.yml`: a copy of
  `monorepo/documents/monkeytype_result/20261123111414.yml` as it is. It is
  public once the repo is.
- Small files written by hand in `yr`'s layout, each for one case:

  | File | Covers |
  | --- | --- |
  | `typos.yml` | `typed`, `fixed`, `error`, extras with `letters`, `-` marks, `extra_fixed`, an early space (`_`), an `inf` word, quoted words such as `"on"` and `"null"`, symbols and capitals |
  | `heatmap_off.yml` | `steps` without `labels` and `colors` |
  | `custom.yml` | no `language` |
  | `chart_error.yml` | `chart_error` and no `chart` |
  | `aborted.yml` | 20 keypresses and `failed (min accuracy)` |
  | `cpm.yml` | `unit: cpm` |
  | `multi.yml` | 3 results, one of them the same as `real_words10.yml` |
  | `not_a_result.yml` | a YAML mapping without `datetime` |
  | `broken.yml` | a YAML syntax error |

- `fixtures.py` writes long results in code (for example 740 chart rows and
  100 words) in the same layout, and a folder of results across two word
  lists and two test types for the Progress tests.

Each PR adds the fixtures and tests its own code needs: `aborted.yml` and
`test_typos` come with PR 2, and the Progress folder and `test_progress` with
PR 3.

### 9.2 Tests

One test file per module, as in `fukuoka_tenki_forcast`:

| Test | Checks |
| --- | --- |
| `test_results` | Every fixture loads or fails as §4.3 says; field mapping; duplicates; order; folder reading with a temporary folder, including re-reading a changed file; `~` and relative paths |
| `test_metrics` | Every row of §5, with edges: a speed equal to the threshold is not slow; 24 and 25 keypresses; `afk_pct` 2 and 2.01; thirds for 2, 3 and 10 words; band labels for the sample steps and for equal edges |
| `test_typos` | Each category at least once; the examples in `analyze.py`'s comments ("/Mlti…" for "Multi…", `sched_yieol`, `addresd`) |
| `test_progress` | Trend groups by word list and test; the mean of up to 10 earlier results; recurring words in 2 of the last 20; aborted results left out |
| `test_charts` | In `chart.to_dict()`: the layers, encodings and dash of each series; independent left and right y scales; the legend selection; the PB line only when §6.5.1 allows it; `inf` words left out; the threshold line |
| `test_history_html` | Each mark's style; the slow outline; tooltip text; a word such as `<script>` comes out escaped |
| `test_palette` | Every colour's contrast against both backgrounds is at least 3:1 |
| `test_ui` | With `AppTest` and `switch_page` on each page file: the no-results message; loading the fixture folder through the folder box; the picker shared by both Result pages; the threshold slider changing the slow list; the goal changing "met" to "missed" |

No whole-chart snapshots. The checks in the "Test and lint" section of the
repo's `README.md` pass: `bazel test //...`, the `.lint` targets, `docs.lint`
and `buildifier.check`.

---

## 10. Build

`BUILD.bazel` follows `vega_lite_chat` and `fukuoka_tenki_forcast`:

- `py_library` `monkeytype_analysis_console_lib`: every module but `main.py`,
  the pages and the tests. Deps: `altair`, `pandas`, `pyyaml`, `streamlit`.
- `streamlit_app` `monkeytype_analysis_console`: `app = "main.py"`,
  `data = glob(["app_pages/*.py"])`, `args = ["--server.address=localhost"]`.
- `py_library` `fixtures`, `testonly`, with `testdata/*.yml` as data.
- A `py_test` per `test_*.py` file, and `test_ui` with `main.py` and the
  pages as data. A `test_suite` `test_all`.
- `markdown_docs` `docs`.

The repo's `README.md` gets a row in its project table and a line under
"Run".

---

## 11. Delivery

Three PRs, one page each (one semantic change per PR, `AGENTS.md`):

| PR | Branch | Contents |
| --- | --- | --- |
| 1 | `feat/monkeytype-console-replay` | This spec as `SPEC.md`, `README.md`, `BUILD.bazel`, reading files (§4), the palette, the slow-word definition, the Result replay page and its charts |
| 2 | `feat/monkeytype-console-analysis` | The rest of §5's per-result definitions, the typo port (§7), the keyboard chart, the Result analysis page |
| 3 | `feat/monkeytype-console-progress` | Trend groups and recurring problems, the Progress charts and page |

---

## 12. Items decided outside the interview

All agreed as drafted on 2026-11-23.

| Item | Section |
| --- | --- |
| `MONKEYTYPE_RESULTS_DIR` presets the folder box | §3.1 |
| Pages are files, not page functions | §3.2 |
| The accuracy goal's range, 0 to 100 in steps of 0.5 | §5 |
| Recurring problems are not filtered by test type | §6.4 |
| No PB line for units other than wpm | §6.5.1 |
| A dotted outline marks slow words in the history | §6.6 |
| The exact palette colours | §6.7 |
