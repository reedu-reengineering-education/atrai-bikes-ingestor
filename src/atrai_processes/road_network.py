import os
import logging
from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor

import osmnx as ox
import networkx as nx
from sqlalchemy import text


from config.db_config import DatabaseConfig


LOGGER = logging.getLogger(__name__)
METADATA = {
    "version": "0.2.0",
    "id": "road_network",
    "title": {
        "en": "road_network",
    },
    "description": {"en": "processes to calculate road network"},
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
        "token": {
            "title": "secret token",
            "description": "identify yourself",
            "schema": {"type": "string"},
        },
        "location": {
            "title": "location",
            "description": "location to get the data from",
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
    "example": {"inputs": {"token": "ABC123XYZ666", "location": "Münster, Germany"}},
}

# {
# 	"inputs": {
# 					"location": [
# 						{"city": "Arnsberg", "county": "Hochsauerlandkreis", "country": "Germany"},
#     				{"city": "Münster", "country": "Germany"},
# 						{"city": "Greifswald", "country": "Germany"},
# 						{"city": "Wiesbaden", "country": "Germany"}
# 					],
# 		      "token": "token"
#         }
# }

class RoadNetwork(AtraiProcessor):
    def __init__(self, processor_def):

        super().__init__(processor_def, METADATA)
        self.secret_token = os.environ.get("INT_API_TOKEN", "token")
        self.db_config = DatabaseConfig()

    def execute(self, data):
        self.check_request_params(data)
        self.location = data.get("location")

        ox.settings.useful_tags_way += ['surface', 'oneway', 'junction', "cycleway"]

        filters = [
            '["highway"~"cycleway"]',
            '["highway"~"path|footway"]["bicycle"~"designated|yes"]',
            '["highway"~"tertiary|unclassified"]["bicycle"!~"use_sidepath"]["cycleway:both"!~"separate"]',
            '["highway"~"secondary|service"]["bicycle"~"yes"]',
            '["highway"~"secondary|service"]["cycleway"~"no|lane|track|opposite_lane|opposite_track|shared_lane|shared_track|share_busway"]',
            '["highway"~"secondary|service"]["cycleway:both"~"no|lane"]',
            '["bicycle_road"~"yes"]',
            '["highway"~"primary|secondary|service"]["cycleway:right"~"lane|share_busway"]',
            '["highway"~"residential|tertiary"]',
            '["oneway:bicycle"~"no"]',
        ]

        road_network = nx.MultiDiGraph()

        for place in self.location:
            G_place = ox.graph_from_place(
                place,
                #custom_filter=filters,
                network_type="bike",
                # simplify=True,
            )
            road_network = nx.compose(road_network, G_place)


        _, edges = ox.graph_to_gdfs(road_network)

        engine = self.db_config.get_engine()

        # we are only interested in the osmid, name and geometry
        LOGGER.debug(edges.columns)
        edges = edges[["osmid", "name", "surface", "geometry", "oneway", "junction", "cycleway"]]

        edges['index'] = edges.index
        self.id_field = 'index'
        self.data = edges
        self.create_collection_entries('road_network')

        edges.to_postgis(f"road_network_{self.campaign}", engine, if_exists="replace", index=False)

        if self.col_create:
            self.update_config()

        #keep simple bike road table for other processes
        bike_road = edges.drop(columns = ['index','surface'])
        bike_road.to_postgis(f"bike_road_network_{self.campaign}", engine, if_exists="replace", index=False)



        outputs = {
            "id": "road_network",
            "status": f"""road network data imported. {edges.shape[0]} edges""",
        }

        return self.mimetype, outputs

    def __repr__(self):
        return f"<RoadNetwork> {self.name}"
