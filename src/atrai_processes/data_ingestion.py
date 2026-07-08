import os
import requests
import logging
import yaml

from .process_base import BaseProcessor, ProcessorExecuteError


LOGGER = logging.getLogger(__name__)


PROCESS_METADATA = {
    "version": "0.3.0",
    "id": "data_ingestion",
    "title": {"en": "data_ingestion"},
    "description": {
        "en": (
            "Run the full analysis pipeline (road network import + analysis processes) "
            "for one or more campaigns/grouptags. Archive ingestion happens automatically "
            "via the scheduler and does not need to be triggered here."
        )
    },
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
        "campaigns": {
            "title": "campaigns",
            "description": (
                "List of grouptag strings to run analyses for, "
                'e.g. ["heilbronn", "muenster"]. '
                "Must match grouptags configured in campaigns.yml."
            ),
            "schema": {"type": "array", "items": {"type": "string"}},
        },
        "processes": {
            "title": "processes",
            "description": (
                'Either the string "all" or a list of process names to run. '
                "Valid names: road_network, distances, statistics, "
                "bumpy-roads, dangerous-places, speed-traffic-flow."
            ),
            "schema": {"type": "string"},
        },
    },
    "outputs": {
        "id": {"title": "ID", "schema": {"type": "string"}},
        "status": {"title": "status", "schema": {"type": "string"}},
    },
    "example": {
        "inputs": {
            "token": "YOUR_TOKEN",
            "campaigns": ["heilbronn"],
            "processes": "all",
        }
    },
}


class DataIngestion(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)
        self.secret_token = os.environ.get("INT_API_TOKEN")
        self.api_url_base = os.environ.get("API_URL", "http://localhost:80")
        self.campaigns_config_path = os.environ.get("CAMPAIGNS_CONFIG", "/app/campaigns.yml")

        # Ordered list of analysis processes to run per campaign
        self.available_processes = [
            "road_network",
            "distances",
            "statistics",
            "bumpy-roads",
            "dangerous-places",
            "speed-traffic-flow",
        ]

    def _load_campaigns_config(self) -> dict:
        """Load campaigns.yml for campaign-specific settings (e.g. road_network locations)."""
        try:
            with open(self.campaigns_config_path) as f:
                return yaml.safe_load(f).get("campaigns", {})
        except Exception as e:
            LOGGER.warning(
                f"Could not load campaigns config from '{self.campaigns_config_path}': {e}"
            )
            return {}

    def execute(self, data):
        mimetype = "application/json"

        token = data.get("token")
        input_campaigns = data.get("campaigns")
        input_processes = data.get("processes")

        if not token:
            raise ProcessorExecuteError("token is required")
        if token != self.secret_token:
            LOGGER.error("WRONG INTERNAL API TOKEN")
            raise ProcessorExecuteError("ACCESS DENIED wrong token")

        # Resolve processes list
        if input_processes == "all":
            processes = self.available_processes
        elif (
            isinstance(input_processes, list)
            and len(input_processes) > 0
            and set(input_processes).issubset(set(self.available_processes))
        ):
            processes = input_processes
        else:
            raise ProcessorExecuteError(
                f"'processes' must be \"all\" or a non-empty list subset of "
                f"{self.available_processes}"
            )

        # Accept any list of grouptag strings as campaigns
        if not isinstance(input_campaigns, list) or len(input_campaigns) == 0:
            raise ProcessorExecuteError(
                "'campaigns' must be a non-empty list of grouptag strings, "
                'e.g. ["heilbronn"]'
            )
        campaigns = input_campaigns

        campaigns_config = self._load_campaigns_config()

        for campaign in campaigns:
            for process in processes:
                endpoint = os.path.join(
                    self.api_url_base, f"processes/{process}/execution?f=json"
                )

                if process == "road_network":
                    campaign_cfg = campaigns_config.get(campaign, {})
                    # Fall back to city=<campaign> if not configured in campaigns.yml
                    road_network_location = campaign_cfg.get(
                        "road_network", [{"city": campaign, "country": "Germany"}]
                    )
                    payload = {
                        "inputs": {
                            "campaign": campaign,
                            "token": token,
                            "location": road_network_location,
                            "col_create": True,
                        }
                    }
                else:
                    payload = {
                        "inputs": {
                            "campaign": campaign,
                            "token": token,
                            "col_create": True,
                        }
                    }

                LOGGER.debug(f"Triggering process '{process}' for campaign '{campaign}'")
                try:
                    r = requests.post(endpoint, json=payload, timeout=7200)
                    r.raise_for_status()
                    LOGGER.info(
                        f"Process '{process}' for campaign '{campaign}' completed"
                    )
                except requests.exceptions.RequestException as e:
                    LOGGER.warning(
                        f"Process '{process}' for campaign '{campaign}' failed: {e}"
                    )

        outputs = {
            "id": "data_ingestion",
            "status": (
                f"Analysis pipeline completed for campaigns={campaigns}, "
                f"processes={processes}"
            ),
        }
        return mimetype, outputs

    def __repr__(self):
        return f"<DataIngestion> {self.name}"
