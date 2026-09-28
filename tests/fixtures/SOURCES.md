# Infrared classifier fixtures

Downloaded unchanged on 2026-09-28. The checks submit four copies of each original still as an integration check, not an accuracy benchmark.

- `hedgehog.jpg`: Alex P. Kok, [Hedgehog at night taken with camera trap](https://commons.wikimedia.org/wiki/File:Hedgehog_at_night_taken_with_camera_trap.jpg), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). [Original JPEG](https://upload.wikimedia.org/wikipedia/commons/5/5d/Hedgehog_at_night_taken_with_camera_trap.jpg). SHA-256: `55d1fadc039f25d2a391795815d3d0fd997307244c542ca247f867f37e184400`.
- `fox.jpg`: US National Park Service, [Fox carrying kit captured on remote wildlife camera during monitoring at Organ Pipe Cactus National Monument in 2021](https://commons.wikimedia.org/wiki/File:Fox_carrying_kit_captured_on_remote_wildlife_camera_during_monitoring_at_Organ_Pipe_Cactus_National_Monument_in_2021._(03b8d99a-ce2b-4b33-bec5-5840354d29a8).JPG), [public domain US federal government work](https://commons.wikimedia.org/wiki/Template:PD-USGov-NPS). [Original JPEG](https://upload.wikimedia.org/wikipedia/commons/8/84/Fox_carrying_kit_captured_on_remote_wildlife_camera_during_monitoring_at_Organ_Pipe_Cactus_National_Monument_in_2021._%2803b8d99a-ce2b-4b33-bec5-5840354d29a8%29.JPG). SHA-256: `0a40e4fe4db6f76b6b44984797535d51713a76636dc6517f075e4cb4e7ae4e74`.

## Live check — 2026-09-28

The orchestrator ran `op run --env-file=.env.tpl -- .venv/bin/python tests/check_classifiers.py` in its authenticated shell and relayed these nonsecret results. Codex could not inherit the service account token. Each request contained four copies of the indicated still.

| Model | Fox still: label, confidence | Hedgehog still: label, confidence |
| --- | --- | --- |
| `nous/google/gemini-3.5-flash-lite` | fox, 0.99 | hedgehog, 1.0 |
| `nous/openai/gpt-5.4-mini` | fox, 0.99 | hedgehog, 0.99 |
| `deepinfra/Qwen/Qwen3-VL-30B-A3B-Instruct` | fox, 0.98 | hedgehog, 0.99 |
| `together/Qwen/Qwen3-VL-32B-Instruct` | pending | pending |

No species disagreements in the completed checks. `--failure` passed: DeepInfra's nonexistent model returned HTTP 404 and the client returned `unclassified, 0.0`.

The orchestrator confirmed the selected IDs in each provider's `/models` catalog. DeepInfra's planned `Qwen/Qwen3-VL-32B-Instruct` returned 404 and was replaced by the served 30B model; `deepinfra/google/gemini-2.5-flash` failed JSON parsing and is excluded. Nous's served Gemini 3.5 Flash-Lite replaces the planned 2.5 Flash-Lite; GPT-5.4 Mini is an additional comparison model requested by the user. Together blocked urllib's default User-Agent with HTTP 403 (Cloudflare 1010); the orchestrator confirmed `foxcam/0.1` fixes catalog access. The client now sends that header on every request. Together's image check remains pending for the orchestrator to run after these commits, as explicitly requested.
