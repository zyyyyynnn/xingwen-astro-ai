# C-04 Mapping Execution Rules

This directory stores the versioned execution policy for Field Manifest mapping and the
unit-conversion implementation catalog. It does not copy canonical fields, aliases,
source priority, companion columns, units, or null/limit/uncertainty declarations.
Those facts remain exclusively in `field-manifest.v1.json`.

The Jupiter/Earth factors use exact nominal constants from IAU 2015 Resolution B3:
equatorial radii for radius units and nominal mass parameters for mass units. They are
conversion constants, not estimates of present physical properties.
