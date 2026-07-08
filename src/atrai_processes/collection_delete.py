import logging
import os
from sqlalchemy import create_engine, MetaData, Table

import requests
import yaml
from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor


LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    "version": "0.2.0",
    "id": "collection dele",
    "title": {
        "en": "col_delete",
    },
    "description": {"en": "process that deletes collections and sources"},
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
    "inputs": {"input": {"title": "result", "description": "The URL of the result", "schema": {"type": "string"}}},
    "outputs": {
        "id": {"title": "ID", "description": "The ID of the process execution", "schema": {"type": "string"}},
        "value": {
            "title": "Value",
            "description": "The URL of the Zarr file in the S3 bucket",
            "schema": {"type": "string"},
        },
    },
    "example": {"inputs": {"result_json": "www.j.son"}},
}


class CollectionDelete(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

        self.serv_config = os.environ.get(key="PYGEOAPI_SERV_CONFIG")
        self.secret_token = os.getenv("INT_API_TOKEN", "token")
        self.col_name = None
        self.delete_source = None
        self.token = None


    def execute(self, data):
        mimetype = "application/json"
        self.col_name = data.get("col_name")
        self.delete_source = data.get("delete_source")
        self.token = data.get("token")

        LOGGER.debug("checking token")
        if self.token != self.secret_token:
            LOGGER.error("WRONG INTERNAL API TOKEN")
            raise ProcessorExecuteError("ACCESS DENIED wrong token")

        with open(self.serv_config, "r") as f:
            data = yaml.safe_load(f)

        resources = data["resources"]


        for col in self.col_name:
            if col in resources.keys():
                del_col = resources.pop(col)
                if self.delete_source:
                    if del_col['providers'][0]['name'] == "PostgreSQL":
                        table_name = del_col['providers'][0]['data']['table']
                        db_config = del_col['providers'][0]['data']
                        connection_string = (
                            f"postgresql://{db_config['user']}:{db_config['password']}@"
                            f"{db_config['host']}:{db_config['port']}/"
                            f"{db_config['dbname']}"
                        )
                        try:
                            engine = create_engine(connection_string)
                            meta = MetaData()
                            table_to_drop = Table(table_name, meta)
                            meta.drop_all(engine, tables=[table_to_drop], checkfirst=True)

                            print(f"Table '{table_name}' has been successfully dropped.")
                        except Exception as e:
                            print(f"Error dropping table: {e}")



        outputs = {"id": "del col", "value": f"{self.col_name} deleted"}
        LOGGER.debug("return")
        return mimetype, outputs

    def __repr__(self):
        return f"<CollectionDelete> {self.name}"