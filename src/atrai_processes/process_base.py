"""
Minimal BaseProcessor / ProcessorExecuteError stub.

Replaces the pygeoapi.process.base dependency so the analysis processes
work without a full pygeoapi installation.
"""


class ProcessorExecuteError(Exception):
    """Raised when a process execution fails."""
    pass


class BaseProcessor:
    """
    Minimal drop-in replacement for pygeoapi.process.base.BaseProcessor.
    Stores metadata and processor_def; subclasses implement execute().
    """

    def __init__(self, processor_def, metadata):
        self.metadata = metadata
        self.name = (
            processor_def.get("name", "")
            if isinstance(processor_def, dict)
            else str(processor_def)
        )

    def execute(self, data):
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"
