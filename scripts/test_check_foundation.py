"""Tests for the repository foundation dependency boundary."""

from __future__ import annotations

import unittest

from scripts.check_foundation import (
    DEPENDENCY_FIELDS,
    FORBIDDEN_FRONTEND_PACKAGES,
    FORBIDDEN_FRONTEND_PACKAGE_PREFIXES,
    is_forbidden_frontend_package,
)


class FrontendFoundationRulesTest(unittest.TestCase):
    def test_dependency_boundary_covers_every_manifest_field(self) -> None:
        self.assertEqual(
            DEPENDENCY_FIELDS,
            (
                "dependencies",
                "devDependencies",
                "peerDependencies",
                "optionalDependencies",
            ),
        )

    def test_forbidden_frontend_packages_cover_exact_and_prefix_forms(self) -> None:
        self.assertTrue(
            all(is_forbidden_frontend_package(name) for name in FORBIDDEN_FRONTEND_PACKAGES)
        )
        self.assertTrue(
            all(
                is_forbidden_frontend_package(prefix + "fixture")
                for prefix in FORBIDDEN_FRONTEND_PACKAGE_PREFIXES
            )
        )


if __name__ == "__main__":
    unittest.main()
