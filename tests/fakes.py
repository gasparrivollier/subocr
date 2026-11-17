from subocr.ocr import OcrResult


class FakeEngine:
    """Returns the given results in call order (repeats the last one when exhausted)."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def read(self, image) -> OcrResult:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r
