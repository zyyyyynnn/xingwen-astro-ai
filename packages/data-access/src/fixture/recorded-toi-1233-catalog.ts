/**
 * Recorded NASA Exoplanet Archive TOI catalog response used by Demo Replay.
 *
 * This is a frozen catalog projection, not a TESS light-curve observation.
 * Values were retrieved from the public TAP `toi` table with the exact query
 * recorded below. Synthetic renderer samples may use these catalog parameters,
 * but must never be presented as measured flux or a scientific model result.
 */

export const TOI_1233_TAP_QUERY =
  "select toi,tid,tfopwg_disp,pl_orbper,pl_trandep,pl_trandurh,pl_rade,st_teff,st_logg,st_rad,st_dist,sectors,rowupdate from toi where toi between 1233 and 1234";

export const TOI_1233_RESPONSE_SHA256 =
  "sha256:99acff9b6caa36283a1e92ec09da5afbb57957f4178aa417ddda7e6ca5694e7a";

export const TOI_1233_RECORDED_AT = "2026-08-30T09:15:00Z";

export interface RecordedToiCatalogRow {
  readonly toi: string;
  readonly ticId: number;
  readonly disposition: "CP";
  readonly orbitalPeriodDays: number;
  readonly transitDepthPpm: number;
  readonly transitDurationHours: number;
  readonly planetRadiusEarth: number;
  readonly stellarEffectiveTemperatureKelvin: number;
  readonly stellarSurfaceGravityLog10Cgs: number;
  readonly stellarRadiusSolar: number;
  readonly stellarDistanceParsec: number;
  readonly rowUpdatedAt: string;
}

export const TOI_1233_CATALOG_ROWS: readonly RecordedToiCatalogRow[] = [
  {
    toi: "1233.01",
    ticId: 260647166,
    disposition: "CP",
    orbitalPeriodDays: 14.1758947,
    transitDepthPpm: 907.1324529,
    transitDurationHours: 3.7543827,
    planetRadiusEarth: 2.6231641,
    stellarEffectiveTemperatureKelvin: 5723.87,
    stellarSurfaceGravityLog10Cgs: 4.438,
    stellarRadiusSolar: 0.864173,
    stellarDistanceParsec: 64.5978,
    rowUpdatedAt: "2024-07-03 12:03:06",
  },
  {
    toi: "1233.02",
    ticId: 260647166,
    disposition: "CP",
    orbitalPeriodDays: 19.5901578,
    transitDepthPpm: 1182.6678641,
    transitDurationHours: 4.002861,
    planetRadiusEarth: 3.0026428,
    stellarEffectiveTemperatureKelvin: 5723.87,
    stellarSurfaceGravityLog10Cgs: 4.438,
    stellarRadiusSolar: 0.864173,
    stellarDistanceParsec: 64.5978,
    rowUpdatedAt: "2024-07-03 12:03:06",
  },
  {
    toi: "1233.03",
    ticId: 260647166,
    disposition: "CP",
    orbitalPeriodDays: 6.2036219,
    transitDepthPpm: 548.9044399,
    transitDurationHours: 3.01098,
    planetRadiusEarth: 2.056748,
    stellarEffectiveTemperatureKelvin: 5723.87,
    stellarSurfaceGravityLog10Cgs: 4.438,
    stellarRadiusSolar: 0.864173,
    stellarDistanceParsec: 64.5978,
    rowUpdatedAt: "2024-07-03 12:03:06",
  },
  {
    toi: "1233.04",
    ticId: 260647166,
    disposition: "CP",
    orbitalPeriodDays: 3.79589,
    transitDepthPpm: 317.5272928,
    transitDurationHours: 2.4602856,
    planetRadiusEarth: 1.553135,
    stellarEffectiveTemperatureKelvin: 5723.87,
    stellarSurfaceGravityLog10Cgs: 4.438,
    stellarRadiusSolar: 0.864173,
    stellarDistanceParsec: 64.5978,
    rowUpdatedAt: "2022-03-30 16:02:02",
  },
] as const;

export const TOI_1233_SHORT_PERIOD_ROW = TOI_1233_CATALOG_ROWS[3]!;
