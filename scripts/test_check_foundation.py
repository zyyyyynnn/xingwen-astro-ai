"""Tests for repository foundation boundaries."""

from __future__ import annotations

import unittest

from scripts.check_foundation import (
    DEPENDENCY_FIELDS,
    FORBIDDEN_FRONTEND_PACKAGES,
    FORBIDDEN_FRONTEND_PACKAGE_PREFIXES,
    WORKFLOW_AUTHORING_ALLOWLIST,
    is_forbidden_frontend_package,
    workflow_authoring_violations,
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


class WorkflowFoundationRulesTest(unittest.TestCase):
    def test_current_authoring_allowlist_is_empty(self) -> None:
        self.assertEqual(WORKFLOW_AUTHORING_ALLOWLIST, frozenset())

    def test_rejects_contents_write(self) -> None:
        self.assertIn(
            "contents: write",
            workflow_authoring_violations(
                ".github/workflows/ci.yml",
                "permissions:\n  contents: write\n",
            ),
        )

    def test_rejects_git_commit_and_push(self) -> None:
        self.assertEqual(
            set(
                workflow_authoring_violations(
                    ".github/workflows/ci.yml",
                    "run: |\n  git commit -m rewrite\n  git push origin HEAD\n",
                )
            ),
            {"git commit", "git push"},
        )

    def test_allows_read_only_validation(self) -> None:
        self.assertEqual(
            workflow_authoring_violations(
                ".github/workflows/ci.yml",
                "permissions:\n  contents: read\n",
            ),
            (),
        )

    def test_ignores_non_workflow_text(self) -> None:
        self.assertEqual(
            workflow_authoring_violations(
                "docs/ci.md",
                "contents: write\ngit commit\ngit push\n",
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
