import os
import logging
from config.db_config import DatabaseConfig
from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor

import pandas as pd

import geopandas as gpd

from sqlalchemy import text

from .statistic_utils import process_tours, tour_stats



LOGGER = logging.getLogger(__name__)

METADATA = {
    "version": "0.2.0",
    "id": "statistics",
    "title": {
        "en": "statistics",
    },
    "description": {"en": "processes to calculate statistics"},
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
        "tag": {
            "title": "tag",
            "description": "tag to filter data",
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
    "example": {"inputs": {"token": "ABC123XYZ666", "tag": "tag"}},
}


class Statistics(AtraiProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, METADATA)


    def execute(self, data):
        # check params
        self.check_request_params(data)
        # load data
        self.check_request_params(data)
        atrai_bike_data = self.load_bike_data()

        try:
            # Step 1: Load raw bike data
            # query = text("SELECT * FROM osem_bike_data WHERE tags LIKE :tag")
            # atrai_bike_data = gpd.read_postgis(
            #     query,
            #     params={"tag": f"%{self.tag}%"},
            #     con=engine,
            #     geom_col="geometry",
            # )
            
            if len(atrai_bike_data) == 0:
                raise ProcessorExecuteError("No data found for the given tag")

            # Step 2: Process tours
            tours = process_tours(atrai_bike_data, interval=12)
            stats = tour_stats(tours)

            # Step 3: Calculate convex hull 
            convex_hull = atrai_bike_data.unary_union.convex_hull

            # Step 4: Create GeoDataFrame containing one row with the bounding box and all the statistics
            tag_value = self.campaign if self.campaign is not None else self.boxId
            if isinstance(tag_value, list):
                ids_to_delete = tag_value
            else:
                ids_to_delete = [tag_value]

            bbox_gdf = gpd.GeoDataFrame(
                {
                    "tag": [tag_value],
                    "statistics": [stats],
                    # add stats to the GeoDataFrame, like with the spread operator in js
                    # **{f"{k}": [v] for k, v in stats.items()},
                    "updatedAt": [pd.Timestamp.now()],
                },
                geometry=[convex_hull],
                crs="EPSG:4326",
            )
        
            # Step 5: Upsert this data into the database, overwrite if exists (by tag). the tag is the primary key
            with self.db_engine.begin() as conn:
                # Check if the table exists
                if not self.db_engine.dialect.has_table(conn, "statistics"):
                    # Create the table if it doesn't exist
                    bbox_gdf.to_postgis(
                        name="statistics",
                        con=conn,
                        if_exists="replace",
                        index=False,
                        dtype={"geometry": "geometry(Polygon, 4326)"},
                    )
                else:
                    # Upsert the data: delete the existing row with the same tag and insert the new one
                    sql = text("DELETE FROM statistics WHERE tag IN :ids")
                    conn.execute(
                        sql,
                        {"ids": tuple(ids_to_delete)},
                    )
                    bbox_gdf.to_postgis(
                        name="statistics",
                        con=conn,
                        if_exists="append",
                        index=False,
                        dtype={"geometry": "geometry(Polygon, 4326)"},
                    )


            outputs = {
                "campaign": self.campaign,
                "status": "success",
                "message": f"Calculated statistics for campaign '{self.campaign}'",
                "statistics": stats
            }

            return self.mimetype, outputs
        finally:
            self.db_engine.dispose()  # Ensure all connections are closed

    def __repr__(self):
        return f"<Statistics> {self.name}"
