/** Generated scientific Demo Replay consumption layer. */

import type {
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  ScientificArtifactRead as ScientificArtifactReadDto,
} from "@xingwen/contracts";
import type { FixtureScientificArtifact } from "./bundle";

import fixtureDocument from "./scientific-artifacts.fixture.json";
import { formalScientificArtifactFixtures } from "./scientific-artifacts-formal";

export const scientificArtifactFixtureProvenance = fixtureDocument.$generated;

const generatedScientificArtifactFixtures: readonly FixtureScientificArtifact[] =
  fixtureDocument.entries.map((entry) => ({
    version: entry.version as unknown as ArtifactVersionDetailDto,
    read: entry.read as unknown as ScientificArtifactReadDto,
    contentBlobs: entry.content_blobs,
  }));

export const scientificArtifactFixtures: readonly FixtureScientificArtifact[] =
  [...generatedScientificArtifactFixtures, ...formalScientificArtifactFixtures];
