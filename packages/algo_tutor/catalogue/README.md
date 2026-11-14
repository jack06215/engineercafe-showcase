# algo_tutor/catalogue

Where problems come from: the bundled manifests, the downloaded LeetCode
problem bank and its rating model, bundled courses, your own study lists,
question packs and first-run setup. The services write through `store/` and
raise the errors in `errors.py`, which the API turns into HTTP errors.

`testdata/` holds a recorded bank download, so the tests need no network.
