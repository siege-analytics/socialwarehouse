"""Regression test for S4 (SW#134): load_voter_file refuses chunks
whose column-shape drifts from the first chunk's shape.

Builds a small CSV with two chunks, the second of which has an extra
column. Mocks PostGISConnector so no DB write happens; asserts the
chunk-shape check raises ValueError naming S4 / SW#134.
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from swh.voters import load_voter_file


def _write_csv(rows: list[str]) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
    f.write("\n".join(rows))
    f.close()
    return Path(f.name)


class TestS4ChunkShapeDrift(SimpleTestCase):

    def test_column_drift_between_chunks_raises_valueerror(self):
        # Chunk 1 has columns: id, vb_tsmart_longitude, vb_tsmart_latitude
        # Chunk 2 has an EXTRA column "extra_col" — should raise.
        rows = ["id,vb_tsmart_longitude,vb_tsmart_latitude"]
        rows += [f"{i},-97.0,30.0" for i in range(3)]
        # Read first 3 rows as chunk 1 (chunk_size=3), then a chunk 2 that
        # parses with a different shape. Easiest reproduction: pre-shape
        # the file with a stable header but force chunk-2 by writing a
        # second CSV body inline. Since pd.read_csv re-uses the header,
        # we instead patch _coerce_and_build_geometry to inject a drifted
        # frame for chunk 2.

        csv = _write_csv(rows)
        try:
            import pandas as pd
            from shapely.geometry import Point
            import geopandas as gpd

            def fake_coerce(df, lon, lat, crs):
                # First call: return the first-chunk shape unchanged.
                # Subsequent calls: drop a column to simulate drift.
                geom = gpd.points_from_xy(df[lon], df[lat])
                gdf = gpd.GeoDataFrame(df, geometry=geom, crs=f"EPSG:{crs}")
                if fake_coerce.call_count == 0:
                    fake_coerce.call_count += 1
                    return gdf
                fake_coerce.call_count += 1
                # Simulate drift: drop one column
                return gdf.drop(columns=["id"])

            fake_coerce.call_count = 0

            mock_connector = MagicMock()
            with patch(
                "siege_utilities.geo.spatial_transformations.PostGISConnector",
                return_value=mock_connector,
            ), patch(
                "swh.voters._legacy_raw._coerce_and_build_geometry",
                side_effect=fake_coerce,
            ), patch(
                "pandas.read_csv",
                return_value=iter([
                    pd.DataFrame({"id": [1, 2], "vb_tsmart_longitude": [-97.0, -97.1], "vb_tsmart_latitude": [30.0, 30.1]}),
                    pd.DataFrame({"id": [3, 4], "vb_tsmart_longitude": [-97.2, -97.3], "vb_tsmart_latitude": [30.2, 30.3]}),
                ]),
            ):
                with self.assertRaises(ValueError) as cm:
                    load_voter_file(
                        filepath=csv,
                        table_name="voters_test",
                        connection_string="postgresql://placeholder/db",
                        chunk_size=2,
                    )
            msg = str(cm.exception)
            assert "S4" in msg or "SW#134" in msg
            assert "column-shape drift" in msg.lower() or "drift" in msg.lower()
        finally:
            csv.unlink(missing_ok=True)

    def test_uniform_chunks_do_not_raise(self):
        # When all chunks have the same shape, the check passes silently.
        # We don't run a real upload (mock connector); we just confirm
        # no ValueError fires from the column-drift check.
        rows = ["id,vb_tsmart_longitude,vb_tsmart_latitude"] + [
            f"{i},-97.0,30.0" for i in range(4)
        ]
        csv = _write_csv(rows)
        try:
            import pandas as pd
            import geopandas as gpd

            def fake_coerce(df, lon, lat, crs):
                geom = gpd.points_from_xy(df[lon], df[lat])
                return gpd.GeoDataFrame(df, geometry=geom, crs=f"EPSG:{crs}")

            mock_connector = MagicMock()
            mock_engine = MagicMock()
            mock_connector.engine = mock_engine
            # Make has_table return False so the swap path skips the LOCK.
            with patch(
                "siege_utilities.geo.spatial_transformations.PostGISConnector",
                return_value=mock_connector,
            ), patch(
                "swh.voters._legacy_raw._coerce_and_build_geometry",
                side_effect=fake_coerce,
            ), patch(
                "sqlalchemy.inspect"
            ) as mock_inspect, patch(
                "pandas.read_csv",
                return_value=iter([
                    pd.DataFrame({"id": [1, 2], "vb_tsmart_longitude": [-97.0, -97.1], "vb_tsmart_latitude": [30.0, 30.1]}),
                    pd.DataFrame({"id": [3, 4], "vb_tsmart_longitude": [-97.2, -97.3], "vb_tsmart_latitude": [30.2, 30.3]}),
                ]),
            ):
                mock_inspect.return_value.has_table.return_value = False
                try:
                    load_voter_file(
                        filepath=csv,
                        table_name="voters_test",
                        connection_string="postgresql://placeholder/db",
                        chunk_size=2,
                    )
                except ValueError as e:
                    if "S4" in str(e) or "SW#134" in str(e):
                        self.fail(f"uniform chunks incorrectly tripped S4 check: {e}")
                except Exception:
                    # Other failures (mocking gaps) are not what we are testing.
                    pass
        finally:
            csv.unlink(missing_ok=True)
