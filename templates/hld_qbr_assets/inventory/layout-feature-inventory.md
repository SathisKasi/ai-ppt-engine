# Layout Feature Inventory

Per-slide layout/category/table/chart flags in one readable list, derived from
`inventory/slide_index.json` + `metadata/slide_NN.json`. See `slide-inventory.md` for titles and
sample-content notes; this file is the flag-only quick reference.

| Slide | Layout | Category | Has Table | Has Chart |
|---|---|---|---|---|
| `slide_00` | Blank | Mandatory | No | No |
| `slide_01` | 9_Section Header | Mandatory | No | No |
| `slide_02` | Title Only | Core | No | No |
| `slide_03` | Title Only | Mandatory | No | No |
| `slide_04` | Title Only | Core | No | No |
| `slide_05` | Title Only | Core | No | No |
| `slide_06` | Title Only | Alternate | No | No |
| `slide_07` | Title Only | Core | No | No |
| `slide_08` | Title Only | Guide-Only | No | No |
| `slide_09` | Title Only | Core | Yes | No |
| `slide_10` | Title Only | Optional | No | No |
| `slide_11` | 1_Section Header_No Image | Divider | No | No |
| `slide_12` | Title Only | Core | Yes | No |
| `slide_13` | Title Only | Core | No | Yes |
| `slide_14` | Title Only | Core | No | No |
| `slide_15` | Title Only | Core | No | No |
| `slide_16` | Title Only | Core | No | No |
| `slide_17` | Title Only | Core | No | No |
| `slide_18` | Title Only | Core | No | No |
| `slide_19` | Title Only | Optional | No | No |
| `slide_20` | Title Only | Core | No | No |
| `slide_21` | 1_Section Header_No Image | Divider | No | No |
| `slide_22` | Title Only | Core | Yes | No |
| `slide_23` | Title Only | Core | Yes | No |
| `slide_24` | 1_Section Header_No Image | Divider | No | No |
| `slide_25` | Title Only | Core | No | No |
| `slide_26` | Title Only | Core | Yes | No |
| `slide_27` | Title Only | Core | Yes | No |
| `slide_28` | 1_Section Header_No Image | Divider | No | No |
| `slide_29` | Title Only | Core | Yes | No |
| `slide_30` | Blank | Mandatory | No | No |
| `slide_31` | 2_Section Header_No Image_Blue BG | Divider | No | No |
| `slide_32` | Title Only | Optional | Yes | No |
| `slide_33` | Title Only | Optional | Yes | No |
| `slide_34` | Blank | Optional | No | No |
| `slide_35` | Title Only | Optional | Yes | No |
| `slide_36` | Title Only | Optional | No | No |
| `slide_37` | Title Only | Optional | No | No |
| `slide_38` | Title Only | Optional | No | No |
| `slide_39` | Title Only | Optional | No | No |
| `slide_40` | Title Only | Optional | No | No |
| `slide_41` | 2_Section Header_No Image_Blue BG | Guide-Only | No | No |
| `slide_42` | Title Only | Guide-Only | No | No |
| `slide_43` | Title Only | Guide-Only | No | No |
| `slide_44` | Title Only | Guide-Only | No | No |
| `slide_45` | Title Only | Guide-Only | No | No |
| `slide_46` | Title Only | Guide-Only | No | No |
| `slide_47` | Title Only | Guide-Only | Yes | No |
| `slide_48` | Title Only | Guide-Only | Yes | No |
| `slide_49` | Title Only | Guide-Only | Yes | No |
| `slide_50` | Title Only | Guide-Only | No | No |
| `slide_51` | Title Only | Guide-Only | No | Yes |
| `slide_52` | Title Only | Guide-Only | No | Yes |
| `slide_53` | Title Only | Guide-Only | No | No |
| `slide_54` | Title Only | Guide-Only | No | No |
| `slide_55` | Title Only | Guide-Only | No | No |
| `slide_56` | Title Only | Guide-Only | No | No |
| `slide_57` | 1_Title and Content | Guide-Only | No | No |
| `slide_58` | Title Only | Guide-Only | No | No |
| `slide_59` | Title Only | Guide-Only | No | No |

Only `Core`/`Optional`/`Alternate` categories are pickable content layouts in
`layout_capability_catalog.json`; `Mandatory` slides are structural (rendered directly by
`core/builders/hld_qbr_generic_builder.py`, never via the catalog); `Divider`/`Guide-Only` are excluded
from the catalog entirely.
