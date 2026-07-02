from lyfta_mcp.models import WorkoutsResponse


def test_workouts_response_accepts_null_current_page():
    payload = {
        "status": True,
        "count": 0,
        "current_page": None,
        "limit": 5,
        "workouts": [],
    }

    response = WorkoutsResponse.model_validate(payload)

    assert response.current_page is None
    assert response.limit == 5
    assert response.workouts == []
