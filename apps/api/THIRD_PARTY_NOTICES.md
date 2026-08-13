# Third-party notices

The bounded scientific-skill adapters use the following direct Python dependencies. Versions are locked by `uv.lock`; this notice records the versions resolved for the current dependency graph.

## Direct dependencies

| Package | Resolved version | License | Upstream |
| --- | ---: | --- | --- |
| Astropy | 8.0.1 | BSD-3-Clause | https://github.com/astropy/astropy |
| Astroquery | 0.4.11 | BSD | https://github.com/astropy/astroquery |
| Photutils | 3.0.0 | BSD-3-Clause | https://github.com/astropy/photutils |
| scikit-learn | 1.9.0 | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn |
| Skyfield | 1.55 | MIT | https://github.com/skyfielders/python-skyfield |
| Skyfield Data | 7.0.0 | MIT | https://github.com/brunobord/skyfield-data |

The project imports these packages through narrow scientific adapters. It does not vendor their source, the MAVIS WWT bundle, ephemeris download scripts, or reference-project model configurations.
