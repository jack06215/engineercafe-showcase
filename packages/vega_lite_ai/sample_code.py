import asyncio

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query

# エージェントの設定
options = ClaudeAgentOptions(
    system_prompt="福岡市オープンデータからグラフを作る",
    allowed_tools=["WebFetch", "Bash", "Write"],
    permission_mode="acceptEdits",
    # サブエージェント（別のコンテキストで動く助手）
    agents={
        "finder": AgentDefinition(
            description="データを探す係",
            prompt="福岡市オープンデータから、使えるデータを探す",
            tools=["WebFetch"],
        )
    },
)


# 指示を送り、進み具合を順に受け取る
async def main() -> None:
    async for message in query(prompt="人口の推移をグラフにして", options=options):
        print(message)


if __name__ == "__main__":
    asyncio.run(main())
