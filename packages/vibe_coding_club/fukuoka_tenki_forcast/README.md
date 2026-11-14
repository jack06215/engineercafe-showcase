# fukuoka_tenki_forcast

The Fukuoka City weather forecast from the Japan Meteorological Agency (JMA),
in the terminal. On a terminal it is a Textual app with three tabs: today and
tomorrow, the week, and the rain radar. When the output is piped, or with
`--plain`, it prints plain text.

```sh
bazel run //packages/vibe_coding_club/fukuoka_tenki_forcast:fukuoka_tenki
```

`DESIGN.md` (in Japanese) covers the scope, the layers, each module and the
data flow. `testdata/` holds recorded JMA responses for the tests.
