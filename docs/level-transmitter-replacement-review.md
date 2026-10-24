# TEP level transmitter replacement review

Status: **preferred family selected for simulation-scope evaluation; no configured instrument approved**.

## Existing assignments

| Signal | Vessel | Benchmark pressure (bar gauge) | Current product |
|---|---|---:|---|
| XMEAS8 | Reactor level | 27.050 | IFM_LW2720 |
| XMEAS12 | Separator level | 26.337 | IFM_LW2720 |
| XMEAS15 | Stripper level | 31.022 | IFM_LW2720 |

The ProductCatalog records IFM_LW2720 process pressure rating as 8 bar. All three vessels have nominal pressures above that figure. Preserve this original reference as provenance; do not treat it as a verified installed instrument.

## Replacement candidates

**Preferred: Endress+Hauser Micropilot FMR62B** radar level transmitter.
- Continuous non-contact measurement of liquid level.
- Manufacturer family specifications: process pressure -1 to +160 bar; maximum measuring distance 80 m; accuracy ±1 mm; 80 GHz radar; 4–20 mA HART available.
- Source: https://www.endress.com/en/field-instruments-overview/level-measurement/Radar-Micropilot-FMR62B
- Technical information: https://bdih-download.endress.com/files/DLA/005056A500261EDFB3E51EEE2F798CBE/TI01684FEN_0524-00.pdf
- Family maxima **must not** be asserted for an unspecified ordering code.

**Alternative: VEGA VEGAPULS 6X**.
- Manufacturer family overview: process pressure up to 160 bar and range up to 120 m, dependent on configuration.
- Some standard applications configurations are only rated to 25 bar and would not meet these nominal vessel pressures.
- Source: https://www.vega.com/api/sitecore/DocumentDownload/Handler?documentContainerId=1008138&documentGroupId=66414&fileExtension=pdf&languageId=2&version=20-01-2025

## Simulation-scope decision

FMR62B is the **preferred candidate family** for XMEAS8, XMEAS12 and XMEAS15. This is not a verified physical installation, not an approved ordering code, and not proof of compatibility with all fault conditions.

Before approving a particular variant even for nominal-range suitability:
1. Identify a documented FMR62B configuration rated above the applicable vessel nominal pressure.
2. Define vessel height and level calibration / percentage scaling. Benchmark XMEAS level percentages cannot be compared directly to radar distance in metres.
3. Verify that the simulated measurement is a continuous liquid level and specify its measurement reference.
4. Keep ECLASS class and property IRDIs unverified until resolved from an authoritative ECLASS release.

No ProductCatalog or AssetInventory references should be overwritten merely on the basis of family-level specifications.
