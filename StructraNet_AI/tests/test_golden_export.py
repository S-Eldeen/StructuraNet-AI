import json
import tempfile
import unittest
from pathlib import Path

from gns3_exporter import convert
from gns3project_validator import GNS3ProjectValidator


class GoldenExportTests(unittest.TestCase):
    def test_golden_minimal_topology_exports_and_validates(self):
        fixture = Path("tests/fixtures/golden_minimal_topology.json")
        data = json.loads(fixture.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "golden_minimal.gns3project"
            result_path = convert(data, str(out_file))
            self.assertTrue(Path(result_path).exists(), "Expected .gns3project output file")

            validator = GNS3ProjectValidator(str(out_file), verbose=False)
            ok = validator.validate()
            self.assertTrue(ok, "Expected validator to pass for golden fixture")


if __name__ == "__main__":
    unittest.main()

