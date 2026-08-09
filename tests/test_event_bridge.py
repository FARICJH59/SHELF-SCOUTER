from shelf_event_bridge import build_observation


def test_build_observation_is_versioned_and_normalized():
    event = build_observation(
        {
            "products": [{
                "name": "Orange Juice",
                "category": "beverages",
                "quantity": 4,
                "shelf_position": "middle",
                "label_text": "Orange Juice",
                "confidence": "high",
            }],
            "shelf_summary": "Refrigerated beverages",
            "total_unique_products": 1,
            "model": "gemma-4-e4b-it",
        },
        {
            "device_id": "cam-01",
            "store_id": "store-01",
            "aisle": "A12",
            "shelf": "S03",
        },
    )

    assert event["schema_version"] == "1.0"
    assert event["event_type"] == "shelf.observation.created"
    assert event["observation"]["device_id"] == "cam-01"
    assert event["observation"]["products"][0]["quantity"] == 4
    assert event["observation"]["total_unique_products"] == 1


def test_missing_optional_context_is_safe():
    event = build_observation({"products": []})
    observation = event["observation"]
    assert observation["store_id"] is None
    assert observation["aisle"] is None
    assert observation["shelf"] is None
    assert observation["products"] == []
