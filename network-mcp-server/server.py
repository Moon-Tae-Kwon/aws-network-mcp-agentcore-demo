"""AWS Network MCP Server — Streamable HTTP mode for AgentCore Runtime."""
import logging, sys
from awslabs.aws_network_mcp_server.tools import cloud_wan, general, network_firewall, transit_gateway, vpc, vpn
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

for module in (general, cloud_wan, network_firewall, transit_gateway, vpc, vpn):
    for tool_name in module.__all__:
        func = getattr(module, tool_name)
        mcp.tool()(func)

def main():
    mcp.run(transport='streamable-http')

if __name__ == '__main__':
    main()
