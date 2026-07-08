from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from analysis_engine.cli import _report_to_dict
from analysis_engine.models import AeoInput, GeoInput, SeoInput
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit

from data_collectors.collectors.pipeline import run_collection_pipeline
from data_collectors.models import CollectionPayload, GeoQuerySpec, KeywordSpec
from data_collectors.providers.dataforseo import DataForSEOClient
from data_collectors.providers.openrouter import OpenRouterClient
from data_collectors.providers.qianfan import QianfanClient


def _load_json_list(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def _require_env(names: list[str]) -> dict[str, str]:
    values = {name: os.getenv(name, "") for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise click.ClickException(f"Missing required environment variables: {', '.join(missing)}")
    return values


def run_collection(
    domain: str,
    url: str,
    brand_name: str,
    keywords_file: Path,
    geo_queries_file: Path,
) -> CollectionPayload:
    env = _require_env(
        [
            "DATAFORSEO_LOGIN",
            "DATAFORSEO_PASSWORD",
            "OPENROUTER_API_KEY",
            "QIANFAN_ACCESS_KEY",
            "QIANFAN_SECRET_KEY",
        ]
    )
    keywords = [KeywordSpec(**item) for item in _load_json_list(keywords_file)]
    geo_queries = [GeoQuerySpec(**item) for item in _load_json_list(geo_queries_file)]
    return run_collection_pipeline(
        domain=domain,
        brand_name=brand_name,
        keywords=keywords,
        geo_queries=geo_queries,
        dataforseo_client=DataForSEOClient(
            login=env["DATAFORSEO_LOGIN"],
            password=env["DATAFORSEO_PASSWORD"],
        ),
        openrouter_client=OpenRouterClient(api_key=env["OPENROUTER_API_KEY"]),
        qianfan_client=QianfanClient(
            access_key=env["QIANFAN_ACCESS_KEY"],
            secret_key=env["QIANFAN_SECRET_KEY"],
        ),
    )


def _payload_to_dict(payload: CollectionPayload) -> dict:
    return {
        "domain": payload.domain,
        "seo": asdict(payload.seo) if payload.seo is not None else None,
        "aeo": asdict(payload.aeo) if payload.aeo is not None else None,
        "geo": asdict(payload.geo) if payload.geo is not None else None,
        "errors": [asdict(item) for item in payload.errors],
    }


@click.group()
def main() -> None:
    pass


@main.command()
@click.option("--domain", required=True)
@click.option("--url", required=True)
@click.option("--brand-name", required=True)
@click.option("--keywords-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
@click.option("--geo-queries-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
def collect(domain: str, url: str, brand_name: str, keywords_file: Path, geo_queries_file: Path) -> None:
    payload = run_collection(
        domain=domain,
        url=url,
        brand_name=brand_name,
        keywords_file=keywords_file,
        geo_queries_file=geo_queries_file,
    )
    click.echo(json.dumps(_payload_to_dict(payload)))


@main.command()
@click.option("--domain", required=True)
@click.option("--url", required=True)
@click.option("--brand-name", required=True)
@click.option("--keywords-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
@click.option("--geo-queries-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), required=True)
def analyze(domain: str, url: str, brand_name: str, keywords_file: Path, geo_queries_file: Path) -> None:
    payload = run_collection(
        domain=domain,
        url=url,
        brand_name=brand_name,
        keywords_file=keywords_file,
        geo_queries_file=geo_queries_file,
    )

    seo = payload.seo or SeoInput(domain=domain)
    aeo = payload.aeo or AeoInput(domain=domain)
    geo = payload.geo or GeoInput(brand_name=brand_name, domain=domain)
    report = compute_composite_score(
        domain,
        score_seo(seo),
        score_aeo(aeo),
        score_geo(geo),
        score_website_audit(url),
    )
    report.recommendations = generate_recommendations(report)
    click.echo(json.dumps(_report_to_dict(report)))
