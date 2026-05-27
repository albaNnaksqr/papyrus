import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.critique_prompts import CRITIQUE_SYSTEM_PROMPT, CRITIQUE_USER_PROMPT


def test_system_prompt_renders():
    rendered = CRITIQUE_SYSTEM_PROMPT.format(domain="computer vision")
    assert "computer vision" in rendered
    assert "20年" in rendered


def test_user_prompt_renders():
    rendered = CRITIQUE_USER_PROMPT.format(paper_content="some paper text here")
    assert "some paper text here" in rendered
    assert "隐含假设" in rendered
    assert "实现陷阱" in rendered
    assert "方法质疑" in rendered
    assert "复现风险" in rendered


def test_prompts_have_no_unreplaced_braces():
    rendered_sys = CRITIQUE_SYSTEM_PROMPT.format(domain="X")
    rendered_usr = CRITIQUE_USER_PROMPT.format(paper_content="Y")
    import re
    assert not re.search(r'\{[a-z_]+\}', rendered_sys)
    assert not re.search(r'\{[a-z_]+\}', rendered_usr)
