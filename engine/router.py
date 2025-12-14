from engine.extractors.universal_extractor import UniversalExtractor

class ExtractorRouter:

    def get(self, url):
        # Future: Replace with ATS-specific extractors
        return UniversalExtractor()
