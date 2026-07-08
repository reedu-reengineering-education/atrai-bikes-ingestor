from .atrai_processor import AtraiProcessor
import json
import logging


LOGGER = logging.getLogger(__name__)

METADATA = {
    "version": "0.2.0",
    "id": "bumpy_roads",
    "title": {
        "en": "bumpy_roads",
    },
    "description": {"en": "evaluates bumpiness of roads"},
    "jobControlOptions": ["sync-execute", "async-execute"],
    "keywords": ["process"],
    "links": [
        {
            "type": "text/html",
            "rel": "about",
            "title": "information",
            "href": "https://example.org/process",
            "hreflang": "en-US",
        }
    ],
    "inputs": {
        "id": {
            "title": "boxid",
            "description": "boxid to get the data from",
            "schema": {"type": "string"},
        },
        "token": {
            "title": "secret token",
            "description": "identify yourself",
            "schema": {"type": "string"},
        },
    },
    "outputs": {
        "id": {
            "title": "ID",
            "description": "The ID of the process execution",
            "schema": {"type": "string"},
        },
        "status": {
            "title": "status",
            "description": "describes process",
            "schema": {"type": "string"},
        },
    },
    "example": {"inputs": {"ids": "ABCDEF123456", "token": "ABC123XYZ666"}},
}

class SimpleProcess(AtraiProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, METADATA)

    def execute(self, data):
        mimetype = "application/json"

        self.check_request_params(data)
        gdf = self.load_data()

        gdf['createdAt'] = gdf['createdAt'].astype(str)

        result = json.loads(gdf.to_json())

        return mimetype, result

    def __repr__(self):
        return f"<SimpleProcess> {self.name}"