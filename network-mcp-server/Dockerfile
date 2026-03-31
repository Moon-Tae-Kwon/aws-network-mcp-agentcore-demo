FROM public.ecr.aws/docker/library/python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir awslabs.aws-network-mcp-server
COPY server.py .
EXPOSE 8000
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
ENV MCP_STATELESS_HTTP=true
ENTRYPOINT ["python", "server.py"]
