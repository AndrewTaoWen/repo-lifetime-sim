# Change impact on a toy repo

`shopkit/` is a tiny shop package: 7 modules, 16 functions and 18 tests, small enough to read in a few minutes. `run_examples.py` makes six edits to it, one at a time. For each edit it asks `repomap.py impact` what the edit affects, without running anything. It then runs the whole suite to see which tests really break, and puts the edit back.

```
run_examples.py --python PY     # PY: an interpreter with pytest, Python 3.12+
```

[Shopkit Impact Examples](https://claude.ai/artifact/5QMS2QWpJhtr9LEPttiyeG) shows all six on the map page, with each selected test marked "broke" or "passed". `shopkit-map.html` is the same page as a file.

## The six edits

| Edit | What it shows | Callers reached | Tests selected | Tests that broke |
|---|---|---|---|---|
| Print prices as `US$` (`format_price`) | A leaf with one caller: only the receipt is affected | `receipt` | 3 of 18 | 2, both selected |
| Bulk discount from 10 items to 11 (`bulk_discount`) | Tests that run the code but don't depend on the changed detail are selected and still pass | `total`, then `receipt` | 5 | 1, selected |
| Round cents down (`round_cents`) | A shared helper: the change ripples up through tax and checkout | `total`, `tax_for`, then `receipt` | 6 | 2, both selected |
| Raise California's tax rate (`RATES` in `tax.py`) | A data change outside any function: every test that runs code in `tax.py` is selected | (none) | 4 | 1, selected |
| Upper-case product codes in `Catalog.add` | `TestCart` builds its catalog once in `setup_class`, so all its tests depend on `add` though none calls it | (none) | 9 | 7, all selected |
| Rename a CSV column (`to_csv`) | No test runs it, so repomap flags it instead of reporting zero impact | (none) | 0 | 0 |

No test that broke was left out of the selection in any of the six. The suite is small, so the selections are a larger share of it than on a real repo. On werkzeug the median selection was 0.6% of the suite.

`impact-*.txt` has the diff and the full `repomap.py impact` output for each edit. For example, rounding:

```
$ repomap.py impact
Changed:
  shopkit/money.py:round_cents  (6 tests)

Callers (pieces that depend on it):
  direct  shopkit.checkout: total
  direct  shopkit.tax: tax_for
    level 2  shopkit.checkout: receipt

Tests that run it: 6 of 18
     4  tests/test_checkout.py
     2  tests/test_money.py
```

## Reading the results

- **Selected but passed is expected.** A test is selected because it runs the changed code. Whether it breaks depends on whether it checks the detail that changed. The bulk-discount tests at checkout buy 2 items, so moving the threshold from 10 to 11 can't change their totals.
- **Data changes select by file.** A change outside any function, such as a constant, can affect any code in that file, so repomap selects every test that runs code there.
- **Shared setup counts.** Before the tracer credited class-scoped setup to every test in the class, the setup-class example would have selected only the first `TestCart` test.
- **Untested code is called out.** When no test runs a changed function, the memory has nothing to go on, and `impact` says so.
