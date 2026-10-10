"""Typed pipeline errors. `code` values are stable and surface in the API error events."""

from __future__ import annotations


class PipelineError(Exception):
    code = "internal"
    http_status = 500

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code

    @property
    def message(self) -> str:
        return str(self)


class ConfigError(PipelineError):
    code = "config"
    http_status = 503


class InvalidTicker(PipelineError):
    code = "invalid_ticker"
    http_status = 400


class TickerNotFound(PipelineError):
    code = "ticker_not_found"
    http_status = 404


class NoTenKFound(PipelineError):
    code = "no_10k"
    http_status = 404


class SecUnavailable(PipelineError):
    code = "sec_unavailable"
    http_status = 503


class ExtractionFailed(PipelineError):
    code = "extraction_failed"
    http_status = 422


class SegmentationFailed(PipelineError):
    code = "segmentation_failed"
    http_status = 422


class DisallowedHost(PipelineError):
    code = "disallowed_host"
    http_status = 500
