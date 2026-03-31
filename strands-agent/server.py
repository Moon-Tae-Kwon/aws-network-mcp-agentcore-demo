import logging, sys
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
url = "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/networkMcpAgentcore-5EHgZt6xTi/invocations?qualifier=DEFAULT&accountId=915370161469"
PROMPT = (
    "You are an expert AWS network engineer. "
    "Use the provided network tools to analyze issues. "
    "Include Mermaid diagrams in mermaid code blocks "
    "to visualize network topology and path analysis."
)
app = BedrockAgentCoreApp()

@app.entrypoint
def agent_invocation(payload, context):
    mcp_factory = lambda: aws_iam_streamablehttp_client(
        terminate_on_close=False,
        aws_service="bedrock-agentcore",
        aws_region="us-east-1",
        endpoint=url
    )
    with MCPClient(mcp_factory) as mcp:
        agent = Agent(
            model=BedrockModel(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                region_name="us-east-1"
            ),
            tools=mcp.list_tools_sync(),
            system_prompt=PROMPT
        )
        prompt = payload.get("prompt", "")
        if not prompt:
            t = payload.get("type", "")
            f = payload.get("fields", {})
            prompt = "Ticket: %s. Fields: %s. Analyze this." % (t, f)
        result = agent(prompt)
        msg = result.message
        if isinstance(msg, dict):
            content = msg.get("content", [])
            text = next((c["text"] for c in content if "text" in c), str(msg))
        else:
            text = str(msg)
        return {"result": text}

app.run()
