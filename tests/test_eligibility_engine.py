from services.eligibility_engine.app.main import check_user_rules, score_user


def test_check_user_rules_department():
    user = {"department": "Finance", "experience_years": 5, "active_task_count": 1}
    rules = {"department": "Finance"}
    assert check_user_rules(user, rules) is True
    rules = {"department": "HR"}
    assert check_user_rules(user, rules) is False

def test_check_user_rules_experience_and_active():
    user = {"department": "Eng", "experience_years": 3, "active_task_count": 2}
    rules = {"min_experience": 4}
    assert check_user_rules(user, rules) is False
    rules = {"max_active_tasks": 1}
    assert check_user_rules(user, rules) is False
    rules = {"min_experience": 2, "max_active_tasks": 3}
    assert check_user_rules(user, rules) is True

def test_score_user_prefers_lower_active_and_higher_experience():
    u1 = {"experience_years": 5, "active_task_count": 5}
    u2 = {"experience_years": 3, "active_task_count": 0}
    assert score_user(u2) > score_user(u1)
