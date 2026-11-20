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


def test_dataset_context_is_given_to_the_model_with_rules():
    from conversation import chat_messages
    context = "Name: stands.csv\nColumns (3):\n- Acres (number)\n- Age (number)\n- TCuFt (number)"
    messages = chat_messages("do the volume per acre", [], dataset_context=context)
    system = messages[0]["content"]
    assert "<selected_dataset>" in system and "TCuFt" in system
    assert "never ask the user to confirm whether these columns exist" in system
    assert "<selected_dataset>" not in chat_messages("hi", [])[0]["content"]


def test_analysis_requests_route_to_data_tools():
    from conversation import is_data_request
    for prompt in ("ok analyze that data for me",
                   "do the volume per acre, age class breakdown, and spatial pattern",
                   "show the age distribution of stands"):
        assert is_data_request(prompt), prompt
    for prompt in ("hi there", "who are you and what do you do?", "what is volume per acre?",
                   "explain age class breakdown", "give me a pizza recipe"):
        assert not is_data_request(prompt), prompt
