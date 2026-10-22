from analysis_engine.geo_judge import heuristic_judge, validate_judge_result


def test_fake_quote_is_not_counted():
    judged = validate_judge_result(
        "Only Acme appears here.",
        {
            "entities": [
                {
                    "name": "Acme",
                    "role": "brand",
                    "recommendation": "positive",
                    "mention_quote": "this sentence was invented",
                    "recommendation_quote": "this sentence was invented",
                    "first_mention_state": "unique",
                    "sentiment": "positive",
                }
            ]
        },
    )

    assert judged["sample_state"] == "unresolved"
    assert judged["counts_for_first_position"] is False
    entity = judged["entities"][0]
    assert entity["valid"] is False
    assert entity["counts_as_mention"] is False
    assert entity["first_mention_state"] == "unresolved"


def test_two_unique_firsts_become_unresolved():
    raw = "Acme is the best. Beta is the best."
    judged = validate_judge_result(
        raw,
        {
            "entities": [
                {
                    "name": "Acme",
                    "role": "brand",
                    "recommendation": "positive",
                    "mention_quote": "Acme is the best.",
                    "recommendation_quote": "Acme is the best.",
                    "first_mention_state": "unique",
                    "sentiment": "positive",
                },
                {
                    "name": "Beta",
                    "role": "competitor",
                    "recommendation": "positive",
                    "mention_quote": "Beta is the best.",
                    "recommendation_quote": "Beta is the best.",
                    "first_mention_state": "unique",
                    "sentiment": "positive",
                },
            ]
        },
    )

    assert judged["counts_for_first_position"] is False
    assert [item["first_mention_state"] for item in judged["entities"]] == ["unresolved", "unresolved"]
    assert all(item["counts_as_mention"] for item in judged["entities"])


def test_heuristic_keeps_a_single_supported_first():
    judged = heuristic_judge(
        "市面上选择不少。最好的选择是 Acme。Beta 也被提到。",
        [
            {"name": "Acme", "role": "brand", "aliases": ["Acme"]},
            {"name": "Beta", "role": "competitor", "aliases": []},
        ],
    )

    acme = next(item for item in judged["entities"] if item["name"] == "Acme")
    beta = next(item for item in judged["entities"] if item["name"] == "Beta")
    assert judged["sample_state"] == "ok"
    assert acme["counts_as_mention"] is True
    assert acme["counts_as_first"] is True
    assert acme["recommendation"] == "positive"
    assert beta["counts_as_mention"] is True
    assert beta["counts_as_first"] is False
    assert "最好的选择是 Acme" in acme["mention_quote"]
