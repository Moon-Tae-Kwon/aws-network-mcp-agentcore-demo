FROM public.ecr.aws/docker/library/python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    strands-agents \
    strands-agents-tools \
    bedrock-agentcore \
    mcp-proxy-for-aws
COPY server.py .
ENTRYPOINT ["python", "server.py"]
