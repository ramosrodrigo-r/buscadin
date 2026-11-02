"""Private, single-turn Hermes process. Never starts or contacts a gateway."""
import argparse
import contextlib
import io
import json
import sys

ROOT = "/home/rodrigo/.hermes/hermes-agent"
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    # Freeze a clean configuration before any runtime/plugin/provider imports.
    from agent.safe_worker_policy import _bind_safe_worker_policy
    _bind_safe_worker_policy(safe_mode=True, ignore_user_config=True, config={
        "model": {"default": args.model, "provider": "openai-codex"},
        "platform_toolsets": {"cli": []}, "mcp_servers": {},
        "agent": {"max_turns": 1},
    })
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from run_agent import AIAgent
        from hermes_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider(requested="openai-codex", target_model=args.model)
        agent = AIAgent(
            model=args.model, provider="openai-codex",
            api_key=runtime.get("api_key"), base_url=runtime.get("base_url"),
            api_mode=runtime.get("api_mode"), enabled_toolsets=[],
            max_iterations=1, run_budget_seconds=270, quiet_mode=True,
            skip_context_files=True, skip_memory=True, skip_background_review=True,
            fallback_model={}, save_trajectories=False,
        )
        if agent.tools or agent.valid_tool_names:
            raise RuntimeError("Unexpected tools: refusing inference")
        if args.check:
            result = {"tools": 0, "provider": agent.provider, "gateway": False}
        else:
            prompt = sys.stdin.read(100_001)
            if not prompt or len(prompt) > 100_000:
                raise ValueError("Invalid prompt size")
            result = agent.run_conversation(prompt)
            if agent.tools or any(m.get("tool_calls") or m.get("role") == "tool"
                                  for m in result.get("messages", [])):
                raise RuntimeError("Unexpected tool use")
            if result.get("failed") or not result.get("completed"):
                raise RuntimeError("Inference did not complete")
            result = json.loads(result["final_response"])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Isolated Hermes generation failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
