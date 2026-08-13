/** Generated scientific Demo Replay consumption layer. */

import type {
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  ScientificArtifactRead as ScientificArtifactReadDto,
} from "@xingwen/contracts";

import fixtureDocument from "./scientific-artifacts.fixture.json";

export const scientificArtifactFixtureProvenance = fixtureDocument.$generated;

export const scientificArtifactFixtures = fixtureDocument.entries.map(
  (entry) => ({
    version: entry.version as unknown as ArtifactVersionDetailDto,
    read: entry.read as unknown as ScientificArtifactReadDto,
    contentBlobs: entry.content_blobs,
  }),
);
