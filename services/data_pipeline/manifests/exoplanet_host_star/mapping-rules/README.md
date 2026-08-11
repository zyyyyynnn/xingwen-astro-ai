# Mapping Execution Rules

This directory stores the versioned execution policy for Field Manifest mapping and the
unit-conversion implementation catalog. It does not copy canonical fields, aliases,
source priority, companion columns, units, or null/limit/uncertainty declarations.
Those facts remain exclusively in `field-manifest.json`.

`mapping-rules.json` is the only executable MappingRuleSet source. It freezes the
`host_star | planet_candidate | planet_assertion` projection matrix, collection-span
numeric tolerance semantics, producer identity, and build capacities. `host_star`
never projects `planet.*`; `planet_candidate` projects only `planet.*`; a PS
`planet_assertion` may retain planet plus explicitly carried star/system context.

`unit-conversions.json` is the only executable conversion catalog. In addition to
the conversion implementations, it freezes Decimal precision, rounding,
negative-zero canonicalization contract, input/significant-digit/exponent/scale
limits, and the maximum plain-decimal output length. The production pipeline loads
both JSON files and compares the complete caller objects, so recomputing a modified
content hash does not authorize a new policy.

The Jupiter/Earth factors use exact nominal constants from IAU 2015 Resolution B3:
equatorial radii for radius units and nominal mass parameters for mass units. They are
conversion constants, not estimates of present physical properties.
