import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_critique_agent_writes_report(tmp_path):
    """Agent reads paper.md, calls LLM, writes critique_report.md."""
    from workflows.agents.critique_agent import run_critique_agent

    paper_md = tmp_path / "paper.md"
    paper_md.write_text("This is a test paper about image classification.")

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "## 1. 隐含假设\n- 假设数据已预处理"

    with patch("workflows.agents.critique_agent.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = fake_response

        result = _run(run_critique_agent(
            paper_dir=str(tmp_path),
            llm_config={"base_url": "http://x", "api_key": "k", "critique_model": "gpt-4o"},
        ))

    assert result["status"] == "success"
    assert "critique_summary" in result
    report_path = tmp_path / "critique_report.md"
    assert report_path.exists()
    assert "隐含假设" in report_path.read_text()


def test_critique_agent_skips_on_missing_paper(tmp_path):
    """Agent returns skipped status (not raise) when no markdown found."""
    from workflows.agents.critique_agent import run_critique_agent

    result = _run(run_critique_agent(
        paper_dir=str(tmp_path),
        llm_config={"base_url": "http://x", "api_key": "k", "critique_model": "gpt-4o"},
    ))

    assert result["status"] == "skipped"
    assert "reason" in result


def test_critique_agent_skips_on_llm_error(tmp_path):
    """Agent returns skipped status (not raise) on LLM failure."""
    from workflows.agents.critique_agent import run_critique_agent

    paper_md = tmp_path / "paper.md"
    paper_md.write_text("Some paper.")

    with patch("workflows.agents.critique_agent.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = _run(run_critique_agent(
            paper_dir=str(tmp_path),
            llm_config={"base_url": "http://x", "api_key": "k", "critique_model": "gpt-4o"},
        ))

    assert result["status"] == "skipped"
