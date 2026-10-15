import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.retraction_watch import clean_reasons, iter_records, parse_date  # noqa: E402

HEADER = ("Record ID,Title,Subject,Institution,Journal,Publisher,Country,Author,URLS,ArticleType,"
          "RetractionDate,RetractionDOI,RetractionPubMedID,OriginalPaperDate,OriginalPaperDOI,"
          "OriginalPaperPubMedID,RetractionNature,Reason,Paywalled,Notes\n")
ROWS = (
    '1,Secret Title,(BLS) Biology,"Example University",J Things,Pub Co,USA,Jane Q Researcher;Sam Other,'
    "http://x,Research Article,5/13/2015 0:00,10.9/r1,0,1/2/2014 0:00,10.1/ABC,0,Retraction,"
    '+Falsification/Fabrication of Data;+Investigation by Journal/Publisher;,No,"some note, with comma"\n'
    "2,T2,S,I,J2,P2,UK,Someone Else,u,Research Article,2020-01-31,unavailable,0,2019-06-01,unavailable,0,"
    "Retraction,+Plagiarism,No,\n"
    "3,T3,S,I,J3,P3,UK,A B,u,Research Article,garbage-date,,0,2018-01-01,10.5/zzz,0,Correction,,No,\n"
)


class RetractionWatchTests(unittest.TestCase):
    def _write(self, text):
        d = tempfile.mkdtemp()
        p = Path(d) / "rw.csv"
        p.write_text(text, encoding="utf-8")
        return p

    def test_records_minimised_and_normalised(self):
        stats = Counter()
        recs = list(iter_records(self._write(HEADER + ROWS), stats))
        self.assertEqual([r["doi"] for r in recs], ["10.1/abc", "10.5/zzz"])  # row 2 has no DOI
        first = recs[0]
        self.assertEqual(first["retraction_date"], 20150513)
        self.assertEqual(first["original_date"], 20140102)
        self.assertEqual(first["nature"], "Retraction")
        self.assertEqual(first["reasons"], ["+Falsification/Fabrication of Data",
                                           "+Investigation by Journal/Publisher"])
        self.assertEqual(stats["skipped:no_original_doi"], 1)
        self.assertEqual(stats["unparsed_retraction_date"], 1)

    def test_no_personal_or_free_text_fields_in_output(self):
        blob = json.dumps(list(iter_records(self._write(HEADER + ROWS))))
        for forbidden in ("Jane", "Researcher", "Sam Other", "Example University", "Secret Title",
                          "some note", "Author", "Institution", "Notes"):
            self.assertNotIn(forbidden, blob)

    def test_missing_column_raises(self):
        with self.assertRaises(ValueError):
            list(iter_records(self._write("Record ID,Journal\n1,J\n")))

    def test_parse_date(self):
        self.assertEqual(parse_date("5/13/2015 0:00"), 20150513)
        self.assertEqual(parse_date("2020-01-31"), 20200131)
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("31/13/2020"))

    def test_clean_reasons(self):
        self.assertEqual(clean_reasons(" a ; b ;;"), ["a", "b"])
        self.assertEqual(clean_reasons(None), [])


if __name__ == "__main__":
    unittest.main()
