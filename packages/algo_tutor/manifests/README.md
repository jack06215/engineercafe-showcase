# algo_tutor/manifests

Data bundled with algo_tutor, read by `catalogue/manifests.py`:

- `topics.yaml`: the 34 topics, with their LeetCode tags and folders.
- `neetcode-problems.json`: every problem of the NeetCode list.
- `study-sets.json`: the bundled courses, such as Hello Interview.
- `zerotrac-ratings.txt`: contest ratings of LeetCode problems.

`catalogue/manifests.py` pins the SHA-256 of the files in `PINNED_SHA256`.
When you replace a file, update its pin. The third-party files keep their
licences in `LICENSE-*.txt`.
