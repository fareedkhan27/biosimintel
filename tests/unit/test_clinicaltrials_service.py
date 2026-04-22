from __future__ import annotations

from app.services.ingestion.clinicaltrials import ClinicalTrialsService


def test_sponsor_matches_exact() -> None:
    assert ClinicalTrialsService._sponsor_matches("Amgen", {"amgen"})


def test_sponsor_matches_substring() -> None:
    assert ClinicalTrialsService._sponsor_matches("Amgen Inc.", {"amgen"})
    assert ClinicalTrialsService._sponsor_matches("Zydus Lifesciences", {"zydus"})


def test_sponsor_matches_reverse_substring() -> None:
    assert ClinicalTrialsService._sponsor_matches("Novartis", {"sandoz", "novartis"})


def test_sponsor_matches_no_match() -> None:
    assert not ClinicalTrialsService._sponsor_matches("Pfizer", {"amgen", "zydus"})
    assert not ClinicalTrialsService._sponsor_matches("Unknown Sponsor", {"amgen"})


def test_sponsor_matches_case_insensitive() -> None:
    assert ClinicalTrialsService._sponsor_matches("AMGEN", {"amgen"})
    assert ClinicalTrialsService._sponsor_matches("amgen", {"AMGEN"})


def test_sponsor_matches_empty() -> None:
    assert not ClinicalTrialsService._sponsor_matches("", {"amgen"})
