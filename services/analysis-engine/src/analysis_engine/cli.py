"""CLI entry point: run the full SEO/AEO/GEO analysis pipeline and print a JSON report."""

from __future__ import annotations

import json
from pathlib import Path

import click

from analysis_engine.models import (
    AeoInput,
    BrandMentionResult,
    CompositeReport,
    FeaturedSnippetHit,
    GeoInput,
    KeywordRanking,
    SeoInput,
)
from analysis_engine.recommendations import generate_recommendations
from analysis_engine.scoring.aeo import score_aeo
from analysis_engine.scoring.composite import compute_composite_score
from analysis_engine.scoring.geo import score_geo
from analysis_engine.scoring.seo import score_seo
from analysis_engine.scoring.website_audit import score_website_audit


def _load_seo_input(path: Path | None, domain: str) -> SeoInput:
    if path is None:
        return SeoInput(domain=domain)
    data = json.loads(path.read_text())
    return SeoInput(
        domain=domain,
        keyword_rankings=[KeywordRanking(**ranking) for ranking in data.get("keyword_rankings", [])],
        indexed_pages_count=data.get("indexed_pages_count"),
        total_pages_count=data.get("total_pages_count"),
    )


def _load_aeo_input(path: Path | None, domain: str) -> AeoInput:
    if path is None:
        return AeoInput(domain=domain)
    data = json.loads(path.read_text())
    return AeoInput(
        domain=domain,
        snippet_hits=[FeaturedSnippetHit(**hit) for hit in data.get("snippet_hits", [])],
        total_keywords_checked=data.get("total_keywords_checked", 0),
    )


def _load_geo_input(path: Path | None, brand_name: str, domain: str) -> GeoInput:
    if path is None:
        return GeoInput(brand_name=brand_name, domain=domain)
    data = json.loads(path.read_text())
    return GeoInput(
        brand_name=brand_name,
        domain=domain,
        mention_results=[BrandMentionResult(**mention) for mention in data.get("mention_results", [])],
    )


def _report_to_dict(report: CompositeReport) -> dict:
    return {
        "domain": report.domain,
        "overall_score": report.overall_score,
        "dimensions": {
            name: {
                "score": breakdown.score,
                "data_complete": breakdown.data_complete,
                "detail": breakdown.detail,
            }
            for name, breakdown in report.dimension_scores.items()
        },
        "recommendations": [
            {
                "priority": recommendation.priority,
                "dimension": recommendation.dimension,
                "title": recommendation.title,
                "description": recommendation.description,
            }
            for recommendation in report.recommendations
        ],
    }


@click.command()
@click.option("--domain", required=True)
@click.option("--url", required=True)
@click.option("--brand-name", required=True)
@click.option("--seo-data", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--aeo-data", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--geo-data", type=click.Path(path_type=Path, dir_okay=False, exists=True))
def analyze(domain: str, url: str, brand_name: str, seo_data: Path | None, aeo_data: Path | None, geo_data: Path | None) -> None:
    seo = score_seo(_load_seo_input(seo_data, domain))
    aeo = score_aeo(_load_aeo_input(aeo_data, domain))
    geo = score_geo(_load_geo_input(geo_data, brand_name, domain))
    website_audit = score_website_audit(url)
    report = compute_composite_score(domain, seo, aeo, geo, website_audit)
    report.recommendations = generate_recommendations(report)
    click.echo(json.dumps(_report_to_dict(report)))

