import pytest
from conversation import chat_messages, is_data_request


@pytest.mark.parametrize("prompt", ["I want a pizza recipe", "show me how to make pizza",
    "make it vegetarian", "What is a tree?", "why do leaves change color?", "hello", "bro"])
def test_general_chat_is_not_a_full_table_query(prompt):
    assert not is_data_request(prompt)


@pytest.mark.parametrize("prompt", ["Chart the sum of acres by age", "Map flowering dogwood trees",
    "Show stands older than 60 with TCuFt above 3000", "Summarize this dataset",
    "Visualize the TreeMap raster for stands older than 60", "Map those", "What CRS does this raster use?",
    "can you map the current data"])
def test_data_actions_still_reach_tools(prompt):
    assert is_data_request(prompt)


def test_context_is_recent_role_aware_and_does_not_duplicate_current_turn():
    history = [{"role":"user","content":"pizza please"},
               {"role":"assistant","content":"Here is a pizza recipe."},
               {"role":"assistant","results":[{"verified_summary":"12 stands", "filtered_df":"secret rows"}]},
               {"role":"user","content":"make it vegetarian"}]
    messages = chat_messages("make it vegetarian", history)
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "make it vegetarian"
    assert sum(m["content"] == "make it vegetarian" for m in messages) == 1
    assert "12 stands" in str(messages)
    assert "secret rows" not in str(messages)
    assert len(chat_messages("new", history, max_chars=3)) == 2
