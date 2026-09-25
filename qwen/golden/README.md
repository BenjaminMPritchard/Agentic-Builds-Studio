Golden test sets: `<job>/NN.json` = `{"input": ..., "expect": {...}}` (`expect` may use
`{"contains": "text"}`). `bin/qwen-run --score` runs them on Ollama and enables jobs at >= 80%.

These are small synthetic seeds based on the Mothers Carpentry material. The guide asks for sets
built from real material (hand-offs on #10, #11, #12, #28, #30, #34; comments on #14, #15, #29;
CI logs): grow each set to 10+ real cases before trusting the pass rate. `mechanical-edit` needs
8 of 10 and stays off.
