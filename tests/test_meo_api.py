from meo_mcp.meo_api import MeoApi


def test_pet_mapping_keeps_only_the_mcp_contract() -> None:
    pet = MeoApi._pet({"id": 7, "name": "Miso", "pet_type": {"name": "Cat"}, "sex": "female", "birthday": "2020-07-01", "photo_url": "https://example.test/miso.jpg", "private": "never expose"})
    assert pet["id"] == 7
    assert pet["species"] == "Cat"
    assert pet["photo_url"].endswith("miso.jpg")
    assert "private" not in pet
