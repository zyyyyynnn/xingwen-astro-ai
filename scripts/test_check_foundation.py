"""Tests for the shared frontend retirement rule source."""

from __future__ import annotations

import unittest

from scripts.check_foundation import (
    DEPENDENCY_FIELDS,
    RETIRED_APP,
    RETIRED_PACKAGES,
    RETIRED_PACKAGE_PREFIXES,
    is_retired_package,
    load_retirement_rules,
)


class FrontendRetirementRulesTest(unittest.TestCase):
    def test_rules_load_from_the_shared_json_source(self) -> None:
        rules = load_retirement_rules()
        self.assertEqual(rules["dependencyFields"], list(DEPENDENCY_FIELDS))

    def test_shared_rules_cover_every_dependency_field(self) -> None:
        self.assertEqual(
            DEPENDENCY_FIELDS,
            (
                "dependencies",
                "devDependencies",
                "peerDependencies",
                "optionalDependencies",
            ),
        )

    def test_shared_rules_cover_exact_prefix_and_path_forms(self) -> None:
        self.assertEqual(RETIRED_APP, "/".join(("apps", "web")))
        self.assertTrue(all(is_retired_package(name) for name in RETIRED_PACKAGES))
        self.assertTrue(
            all(is_retired_package(prefix + "fixture") for prefix in RETIRED_PACKAGE_PREFIXES)
        )


if __name__ == "__main__":
    unittest.main()
