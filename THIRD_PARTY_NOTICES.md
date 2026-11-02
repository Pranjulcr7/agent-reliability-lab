# Third-party notices

This repository contains original code and depends on the following packages. No third-party
source files are copied into this repository; all are imported as dependencies (versions pinned in `uv.lock`).

| Package | Version tested | License | Use |
|---|---|---|---|
| [smolagents](https://github.com/huggingface/smolagents) | 1.26.0 | Apache-2.0 | agent runtime (`ToolCallingAgent`, `Model`, `Tool`) |
| [pydantic](https://github.com/pydantic/pydantic) | 2.13.5 | MIT | tool argument / response schemas |
| [PyYAML](https://github.com/yaml/pyyaml) | 6.0.3 | MIT | config files |
| [Gradio](https://github.com/gradio-app/gradio) (optional `viewer`) | 6.28.0 | Apache-2.0 | trace replay viewer |
| [Matplotlib](https://matplotlib.org) (optional `report`) | 3.11.2 | Matplotlib License (PSF-style) | comparison chart |
| [pytest](https://pytest.org) (dev) | 8.x | MIT | tests |

Optional, not installed by default: `transformers`/`torch` (Apache-2.0 / BSD-3-Clause) through
`smolagents[transformers]`, and `openai` (Apache-2.0) through `smolagents[openai]`.

The chart colours are taken from a palette whose colour-vision-deficiency separation was checked with a
validator script. The script was used as a tool and is not part of this repository.
